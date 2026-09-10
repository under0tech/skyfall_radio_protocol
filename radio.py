import random
import struct
import time

from machine import UART, Pin


def crc16(data: bytes) -> int:
    """Calculate standard CRC-16-CCITT."""
    crc = 0xFFFF

    for byte in data:
        crc ^= byte << 8

        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF

    return crc


class RadioHC12:
    """
    HC-12 radio driver for microcontrollers.

    Provides UART communication with HC-12 modules
    and supports reliable data transmission with acknowledgements.
    """

    PREAMBLE = b'\xaa\x55'

    # Transport layer control identifiers
    TRANSPORT_DATA = b'\x01'
    TRANSPORT_ACK = b'\x02'

    def __init__(
        self,
        uart_id,
        tx,
        rx,
        baudrate=9600,
        my_id=0,
        allowed_devices=None
    ):
        """
        Initialize HC-12 radio node.
        
        :param uart_id:
            UART peripheral number, e.g. 0 or 1.
        :param tx:
            GPIO pin number used for UART TX.
        :param rx:
            GPIO pin number used for UART RX.
        :param baudrate:
            UART communication speed in bits per second.
            Default is 9600.
        :param my_id:
            Local device ID, 0-254.
        :param allowed_devices:
            Optional list of authorized remote device IDs.
            None means accept all devices.
        """

        self.uart = UART(
            uart_id,
            baudrate=baudrate,
            tx=Pin(tx),
            rx=Pin(rx),
            rxbuf=512
        )

        self.my_id = my_id
        self.baudrate = baudrate
        self.allowed_devices = (
            set(allowed_devices)
            if allowed_devices is not None
            else None
        )

        # Persistent receive buffer.
        # Data remains here until a complete frame is available.
        self.rx_buffer = bytearray()

    # =========================================================================
    # DATA LINK LAYER
    # =========================================================================

    def send_frame(self, payload: bytes) -> bool:
        """
        Send one framed packet.

        Frame format:

        +----------+--------+-------------+---------+
        | PREAMBLE | LENGTH |   PAYLOAD   |  CRC16  |
        |  2 bytes | 1 byte | 1-240 bytes | 2 Bytes |
        +----------+--------+---------+-------------+
        """

        length = len(payload)

        if length == 0 or length > 240:
            return False
        
        header = self.PREAMBLE + bytes([length])

        crc = crc16(payload)
        crc_bytes = struct.pack('>H', crc)

        frame = header + payload + crc_bytes

        self.uart.write(frame)

        return True

    def read_frame(self):
        """
        Frame reader.

        Returns:
            payload bytes if a complete valid frame is available
            None if no complete frame is currently available
        """

        # Read all currently available UART data
        if self.uart.any():
            data = self.uart.read()

            if data:
                self.rx_buffer.extend(data)

        # -------------------------------------------------------------
        # Find frame preamble: AA 55
        # -------------------------------------------------------------

        while len(self.rx_buffer) >= 2:

            if (
                self.rx_buffer[0] == 0xAA
                and self.rx_buffer[1] == 0x55
            ):
                break

            # Discard one byte
            self.rx_buffer = self.rx_buffer[1:]

        # Preamble is not complete yet
        if len(self.rx_buffer) < 2:
            return None

        # Need AA 55 LENGTH
        if len(self.rx_buffer) < 3:
            return None

        length = self.rx_buffer[2]

        # Reject invalid length
        if length == 0 or length > 240:
            self.rx_buffer = self.rx_buffer[1:]
            return None

        # Complete frame:
        # AA 55 + LENGTH + PAYLOAD + CRC16
        frame_size = 2 + 1 + length + 2

        # Frame is incomplete
        if len(self.rx_buffer) < frame_size:
            return None

        # -------------------------------------------------------------
        # Extract payload
        # -------------------------------------------------------------

        payload_start = 3
        payload_end = payload_start + length

        payload = bytes(
            self.rx_buffer[payload_start:payload_end]
        )

        # -------------------------------------------------------------
        # Extract CRC
        # -------------------------------------------------------------

        crc_received = struct.unpack(
            '>H',
            self.rx_buffer[payload_end:payload_end + 2]
        )[0]

        # Remove complete frame from buffer
        self.rx_buffer = self.rx_buffer[frame_size:]

        # -------------------------------------------------------------
        # Validate CRC
        # -------------------------------------------------------------

        if crc16(payload) != crc_received:
            return None

        return payload

    # =========================================================================
    # NETWORK + TRANSPORT LAYER
    # =========================================================================

    def send_reliable_block(
        self,
        dst_id: int,
        block: bytes,
        max_retries: int = 5
    ) -> bool:
        """
        Send one reliable block to a destination.

        :param dst_id:
            Destination device ID, 0-254.
        :param block:
            Data block to send.
        :param max_retries:
            Maximum number of retransmission attempts.
            Default is 5.

        Block format:

        +--------+--------+-------------+-------------------+
        | DST_ID | SRC_ID |  TRANSPORT  |      PAYLOAD      |
        | 1 byte | 1 byte |   1 byte    |  up to 237 bytes  |
        +--------+--------+-------------+-------------------+

        Returns:
            True if the block was successfully acknowledged,
            otherwise False.
        """

        if len(block) > 237:
            return False

        # Build network + transport payload.
        transport_payload = (
            bytes([dst_id, self.my_id])
            + self.TRANSPORT_DATA
            + block
        )

        # Initial random backoff window.
        backoff_min = 20
        backoff_max = 60

        for attempt in range(max_retries):

            # ---------------------------------------------------------
            # Send data frame
            # ---------------------------------------------------------

            if not self.send_frame(transport_payload):
                return False

            # ---------------------------------------------------------
            # Wait until the HC-12 has physically finished transmitting.
            #
            # UART uses approximately 10 bits per byte with 8N1:
            # 1 start + 8 data + 1 stop.
            # ---------------------------------------------------------

            frame_size = len(transport_payload) + 5

            tx_time_ms = int(frame_size * 10 * 1000 / self.baudrate)

            # Additional time for HC-12 turnaround.
            time.sleep_ms(tx_time_ms + 30)

            # ---------------------------------------------------------
            # Wait for ACK
            # ---------------------------------------------------------

            start_wait = time.ticks_ms()

            while time.ticks_diff(
                time.ticks_ms(),
                start_wait
            ) < 500:

                incoming_frame = self.read_frame()

                if incoming_frame and len(incoming_frame) >= 3:

                    rx_dst = incoming_frame[0]
                    rx_src = incoming_frame[1]
                    rx_flag = incoming_frame[2:3]

                    # Check that this ACK belongs to our transmission.
                    if (
                        rx_dst == self.my_id
                        and rx_src == dst_id
                        and rx_flag == self.TRANSPORT_ACK
                    ):
                        return True

                # Keep the loop responsive.
                time.sleep_ms(2)

            # ---------------------------------------------------------
            # ACK was not received.
            # Retry after randomized backoff.
            # ---------------------------------------------------------

            if attempt < max_retries - 1:

                random_backoff = random.randint(
                    backoff_min,
                    backoff_max
                )

                time.sleep_ms(random_backoff)

                # Exponential backoff.
                backoff_min *= 2
                backoff_max *= 2

        return False

    def receive_reliable_block(self):
        """
        Reliable receive function.

        Returns:
            (sender_id, payload)
        or:
            None
            if no complete valid packet is currently available.
        """

        incoming_frame = self.read_frame()

        if not incoming_frame:
            return None

        # Minimum network + transport header.
        if len(incoming_frame) < 3:
            return None

        # -------------------------------------------------------------
        # Extract network header
        # -------------------------------------------------------------

        rx_dst = incoming_frame[0]
        rx_src = incoming_frame[1]
        rx_flag = incoming_frame[2:3]

        # -------------------------------------------------------------
        # Security filter
        # -------------------------------------------------------------

        if (
            self.allowed_devices is not None
            and rx_src not in self.allowed_devices
        ):
            # Silently reject unauthorized devices.
            return None

        # -------------------------------------------------------------
        # Destination filter
        # -------------------------------------------------------------

        if rx_dst != self.my_id and rx_dst != 0xFF:
            # Packet belongs to another device.
            return None

        # -------------------------------------------------------------
        # DATA packet
        # -------------------------------------------------------------

        if rx_flag == self.TRANSPORT_DATA:

            # HC-12 is half-duplex.
            # Give the transceiver time to switch from RX to TX.
            time.sleep_ms(50)

            # ACK packet:
            #
            # [destination = sender]
            # [source = me]
            # [ACK flag]
            #
            ack_packet = (
                bytes([rx_src, self.my_id])
                + self.TRANSPORT_ACK
            )

            self.send_frame(ack_packet)

            # Remove:
            #
            # DST_ID
            # SRC_ID
            # TRANSPORT_FLAG
            #
            # and return only application data.
            pure_payload = incoming_frame[3:]

            return (rx_src, pure_payload)

        # Ignore unknown transport flags.
        return None