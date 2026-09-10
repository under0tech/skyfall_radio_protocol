import os
import struct

from utime import sleep, ticks_ms, ticks_diff
from radio import RadioHC12


class Skyfall:
    """
    Skyfall protocol for transmitting reliable, encrypted data and files
    over an HC-12 radio link.
    """

    # Message type identifiers
    MSG_TEXT = b'\x01'
    MSG_FILE = b'\x02'

    # Encryption type identifiers
    CRYPTO_NONE = b'\x00'
    CRYPTO_XOR  = b'\x01'

    # Control flags
    FLAG_SINGLE_OR_MID = b'\x00'  # Single message packet or middle file chunk
    FLAG_EOF           = b'\x01'  # End of File / Final stream chunk

    def __init__(self, radio_instance: RadioHC12, encryption_keys=None):
        """
        Initializes the Skyfall protocol.
        
        :param radio_instance: 
            An initialized instance of the RadioHC12 class.
        :param encryption_keys: 
            A dictionary mapping integer device IDs to their 
            respective unique byte keys. E.g., {2: b"key-abc"}.
            Defaults to None if no encryption keys are configured.
        """
        self.radio = radio_instance
        self.keys_table = encryption_keys if encryption_keys is not None else {}

    def _xor_cipher(self, data: bytes, key: bytes) -> bytes:
        """
        Applies polyalphabetic stream cipher using bitwise XOR with a repeating key.
        """
        return bytes(data[i] ^ key[i % len(key)] for i in range(len(data)))

    # =========================================================================
    # TRANSMISSION (PACKING & ENCRYPTION)
    # =========================================================================

    def send_secured_message(self, dst_id: int, msg_type: bytes, chunk_id: int, 
                             flags: bytes, raw_payload: bytes, use_crypto: bool = False) -> bool:
        """
        Structures the Skyfall packet, optionally encrypts the payload,
        and passes the resulting block to the reliable transport engine.

        :param dst_id:
            Destination device ID, 0-254.

        :param msg_type:
            Message type identifier.
            MSG_TEXT for a text message or MSG_FILE for a file transfer.

        :param chunk_id:
            Chunk identifier used to identify the message or file chunk.

        :param flags:
            Control flags.
            FLAG_SINGLE_OR_MID for a single message or middle file chunk.
            FLAG_EOF for the final file or stream chunk.

        :param raw_payload:
            Raw data to be transmitted.
            Maximum size is 232 bytes.

        :param use_crypto:
            If True, encrypts the payload before transmission.
            Default is False.

        Skyfall packet:

        +----------+-------------+----------+---------+-------------+
        | MSG TYPE | CRYPTO TYPE | CHUNK ID |  FLAGS  |   PAYLOAD   |
        |  1 byte  |   1 byte    |  2 bytes | 1 byte  | 1-232 bytes |
        +----------+-------------+----------+---------+-------------+

        Maximum raw_payload size: 232 bytes
        (237-byte transport limit - 5-byte Skyfall header).

        Returns:
            True if the message was successfully transmitted and acknowledged,
            otherwise False.
        """
        
        if len(raw_payload) > 232:
            return False

        crypto_type = self.CRYPTO_NONE
        processed_payload = raw_payload

        # Evaluate if encryption is requested
        if use_crypto:
            key = self.keys_table.get(dst_id)
            if not key:
                return False
            
            crypto_type = self.CRYPTO_XOR
            processed_payload = self._xor_cipher(raw_payload, key)

        # Assemble the 5-byte Skyfall-protocol header
        header = msg_type + crypto_type + struct.pack('>H', chunk_id) + flags
        skyfall_packet = header + processed_payload

        # Pass complete block assembly down to HC-12 driver
        return self.radio.send_reliable_block(dst_id=dst_id, block=skyfall_packet)

    # =========================================================================
    # RECEIVING (DECRYPTION & FILTERING)
    # =========================================================================

    def receive_secured_message(self) -> tuple[int, bytes, int, bytes, bytes] | None:
        """
        Receives a Skyfall packet, optionally decrypts the payload
        if encryption is flaged, and returns the pure data.
        
        Returns:
            Tuple of 
            (sender_id, msg_type, chunk_id, flags, pure_data_bytes)
        or:
            None 
            if no valid message is available.
        """

        transport_result = self.radio.receive_reliable_block()
        if not transport_result:
            return None

        sender_id, skyfall_packet = transport_result

        # Enforce basic structural threshold constraint 
        # (Must contain at least 5B header)
        if len(skyfall_packet) < 5:
            return None

        # Extract header properties
        msg_type    = skyfall_packet[0:1]
        crypto_type = skyfall_packet[1:2]
        chunk_id    = struct.unpack('>H', skyfall_packet[2:4])[0]
        flags       = skyfall_packet[4:5]
        
        encrypted_payload = skyfall_packet[5:]

        # Decrypt if encrypted
        if crypto_type == self.CRYPTO_XOR:
            key = self.keys_table.get(sender_id)
            if not key:
                return None
            
            # Decrypt payload
            pure_payload = self._xor_cipher(encrypted_payload, key)
        
        elif crypto_type == self.CRYPTO_NONE:
            pure_payload = encrypted_payload

        else:
            return None

        # Validation
        if msg_type not in (self.MSG_TEXT, self.MSG_FILE):
            return None
            
        if flags not in (self.FLAG_SINGLE_OR_MID, self.FLAG_EOF):
            return None

        # If validated, return tuple
        return (sender_id, msg_type, chunk_id, flags, pure_payload)

    # =========================================================================
    # WRAPPERS (USAGE)
    # =========================================================================

    def broadcast_secured_message(self, dst_id: int, message) -> bool:
        """
        Broadcasts a secured message to the specified destination.

        :param dst_id:
            Destination device ID, 0-254.

        :param message:
            Message data to be broadcasted.

        Returns:
            True if the message was successfully transmitted,
            otherwise False.
        """
        
        is_success = self.send_secured_message(
            dst_id=dst_id,
            msg_type=Skyfall.MSG_TEXT,
            chunk_id=0,
            flags=Skyfall.FLAG_SINGLE_OR_MID,
            raw_payload=message.encode("utf-8"),
            use_crypto=True)
  
        if not is_success:
            print("Broadcasting: failed or aborted.")
        else:
            print("Broadcasting: successful.")
            return True

        return False

    def broadcast_secured_file(self, dst_id: int, filename) -> bool:
        """
        Broadcasts a secured file to the specified destination in chunks.

        :param dst_id:
            Destination device ID, 0-254.

        :param filename:
            Name or path of the file to be transmitted.

        Returns:
            True if the entire file was successfully transmitted,
            otherwise False.

        Each file chunk contains up to 232 bytes of payload data.
        The final chunk is marked with FLAG_EOF.
        """

        chunk_counter=0
        try:
            with open(filename, "rb") as f:
                while True:
                    chunk_data = f.read(232)
                    if not chunk_data:
                        break
                        
                    chunk_counter += 1
                    
                    next_peek = f.read(0)
                    current_position = f.tell()
                    next_bytes = f.read(1)
                    
                    if len(next_bytes) == 0:
                        control_flag = Skyfall.FLAG_EOF
                        print(f"Processing FINAL chunk #{chunk_counter} ({len(chunk_data)} bytes)")
                    else:
                        control_flag = Skyfall.FLAG_SINGLE_OR_MID
                        print(f"Processing mid-stream chunk #{chunk_counter} ({len(chunk_data)} bytes)")
                    
                    f.seek(current_position)
                    
                    is_success = self.send_secured_message(
                        dst_id=dst_id,
                        msg_type=Skyfall.MSG_FILE,
                        chunk_id=chunk_counter,
                        flags=control_flag,
                        raw_payload=chunk_data,
                        use_crypto=True
                    )
                    
                    if is_success:
                        print(f"   [ACK] Chunk #{chunk_counter} delivered.")
                    else:
                        print(f"   [FAIL] Transmission error on chunk #{chunk_counter}. Halting transfer.")
                        return False

                    sleep(0.02)
                        
            print("File transfer finished.")

        except OSError:
            print(f"Could not locate '{filename}' in storage.")
            return False

        return True
   
    def read_secured_packages(self, file_prefix='',
                                    file_ext='',
                                    on_message=None,
                                    uart_timeout=5000):
        """
        Reads and processes incoming secured radio messages.

        Continuously receives secured messages from the radio until
        the UART remains inactive for the specified timeout period.

        Text messages are decoded as UTF-8 and passed to the callback.
        File messages are received as chunks and written directly to
        storage. File reception is completed when a chunk with FLAG_EOF
        is received.

        Files are stored using the following naming scheme:

            <file_prefix><sender_id>.<file_ext>

        Separate file handlers are maintained for each sender device,
        allowing file transfers from multiple devices to be stored
        independently.

        :param file_prefix:
            Prefix used when creating received file names.

        :param file_ext:
            File extension used when creating received file names.

        :param on_message:
            Callback invoked when a text message is received
            or a file transfer is completed.

            The callback receives two arguments:

                on_message(message_type, data)

            For text messages, data contains decoded message text.

            For completed file transfers, data contains the
            generated output filename.

            Attantion: If None, no messages are processed.
            Default is None.

        :param uart_timeout:
            Maximum time in milliseconds to wait for additional
            incoming data after the last successfully received
            message.
            Default is 5000 ms.
        """

        if on_message is None:
            return

        if not hasattr(self, 'file_handlers'):
            self.file_handlers = {}

        last_uart_time = ticks_ms()

        while (self.radio.uart.any() or
                ticks_diff(ticks_ms(), last_uart_time) <= uart_timeout):

            incoming = self.receive_secured_message()

            if incoming is not None:

                sender_id, msg_type, chunk_id, flags, pure_data = incoming

                # Text incoming
                if msg_type == Skyfall.MSG_TEXT:
                    try:
                        text_message = pure_data.decode('utf-8')

                        print(f"[TEXT ALERT] Node ID {sender_id} message: '{text_message}'")

                        on_message(
                            Skyfall.MSG_TEXT,
                            f"Node ID {sender_id} sent: '{text_message}'"
                        )

                    except UnicodeError:
                        print(f"[Error] Received unparseable text framework block from Node ID {sender_id}.")

                # File chunk incoming
                elif msg_type == Skyfall.MSG_FILE:

                    if file_prefix == '' or file_ext == '':
                        break

                    output_filename = file_prefix + f'{sender_id}' + f'.{file_ext}'

                    if chunk_id == 1:

                        print(f"[FILE INBOUND] Starting data collection into '{output_filename}'...")

                        if sender_id in self.file_handlers:
                            try:
                                self.file_handlers[sender_id].close()
                            except:
                                pass

                        if output_filename in os.listdir():
                            os.remove(output_filename)

                        self.file_handlers[sender_id] = open(
                            output_filename,
                            "wb"
                        )

                    if sender_id in self.file_handlers:

                        self.file_handlers[sender_id].write(pure_data)
                        self.file_handlers[sender_id].flush()

                        print(f" Stored secure block #{chunk_id} ({len(pure_data)} bytes) from Node {sender_id}")

                    else:
                        print(f" [Error] Received chunk #{chunk_id} from Node {sender_id} but no file handler exists!")

                    if flags == Skyfall.FLAG_EOF:

                        print(
                            "[SUCCESS] File transmission complete! "
                            "Closing stream descriptor pipeline."
                        )

                        if sender_id in self.file_handlers:
                            self.file_handlers[sender_id].close()
                            del self.file_handlers[sender_id]

                        on_message(
                            Skyfall.MSG_FILE,
                            f'{output_filename}'
                        )

                last_uart_time = ticks_ms()

            sleep(0.02)