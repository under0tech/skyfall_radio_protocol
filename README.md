# Skyfall radio protocol
Protocol for transmitting/receiving encrypted data and files over HC-12 radio.

Designed for use on microcontrollers like Raspberry Pi Pico or ESP32. Supports acknowledgment (confirmation) of packet transmission, filtering radio nodes by their IDs, and encryption/decryption of packets for secure communication between a radio server and radio clients (IoT devices).

The primary application areas are IoT devices, perimeter security systems, greenhouses, yards, farms, and any other objects where secure and reliable communication is required but traditional internet connectivity is not available.

## Inheritance

A protocol built on top of the [**HC-12 radio driver**](radio.py) for microcontrollers. It inherits the driver's functionality (radio group filtering and acknowledgments) and limitations (a 240-byte payload per message/chunk) at the Data Link and Network/Transport layers.

Skyfall acts as a higher-level wrapper (Presentation layer) over the driver, adding functionality such as encryption/decryption, file transfer using chunks, and simultaneous reception of messages and multiple files from different IoT clients.

## Packets

The HC-12 radio driver operates across the **Data Link** and **Network/Transport** layers of the OSI model, while the **Skyfall protocol** operates as a higher-level **Presentation layer**. Each layer adds its own header and payload structure while respecting the payload limitations of the layer below it.

### HC-12 radio packets

#### Data Link layer

The *Data Link layer* is responsible for radio frame structure, payload length identification, and packet integrity using CRC16.

```text
+----------+--------+-------------+---------+
| PREAMBLE | LENGTH |   PAYLOAD   |  CRC16  |
|  2 bytes | 1 byte |  1-240 bytes| 2 bytes |
+----------+--------+-------------+---------+
```
- **PREAMBLE** - 0xAA55, identifies the beginning of a radio frame.  
- **LENGTH** - size of the payload in bytes.  
- **PAYLOAD** - data passed to the Network/Transport layer.  
- **CRC16** - CRC-16 checksum used to detect transmission errors.  

Maximum payload size: **240 bytes**.

#### Network/Transport layers

The *Network/Transport layer* identifies the source and destination radio nodes and defines the transport type.

```text
+--------+--------+-----------+-------------------+
| DST_ID | SRC_ID | TRANSPORT |      PAYLOAD      |
| 1 byte | 1 byte |  1 byte   |  up to 237 bytes  |
+--------+--------+-----------+-------------------+
```
- **DST_ID** - destination radio node ID.  
- **SRC_ID** - source radio node ID.  
- **TRANSPORT** - transport packet type.  
- **PAYLOAD** - data passed to the Skyfall-protocol.  

The total *Network/Transport payload* must fit within the **240-byte** of *Data Link payload limit*. Maximum *Network/Transport payload* size: **237 bytes**.

### Skyfall protocol packets

#### Presentation layer

The **Skyfall protocol** operates above the [HC-12 driver](radio.py) and adds encryption, message types, file chunking, and packet flags.

```text
+----------+-------------+----------+---------+-------------+
| MSG TYPE | CRYPTO TYPE | CHUNK ID |  FLAGS  |   PAYLOAD   |
|  1 byte  |   1 byte    |  2 bytes | 1 byte  |  1-232 bytes|
+----------+-------------+----------+---------+-------------+
```
- **MSG TYPE** - identifies the message type, such as text or file data.  
- **CRYPTO TYPE** - identifies the encryption method used for the payload.  
- **CHUNK ID** - sequential identifier of the message or file chunk.  
- **FLAGS** - indicates packet state, such as a single packet, intermediate chunk, or end-of-file.  
- **PAYLOAD** - encrypted or unencrypted application data.  

Maximum *Skyfall payload* size: **232 bytes**.

#### Packets incapsulation

The **Skyfall packet** is encapsulated inside the *Network/Transport payload* of HC-12 radio frame/packet:

```text
HC-12 Data Link packet (245 bytes) 
└── Network/Transport packet (240 bytes)
    └── Skyfall packet (237 bytes)
        └── Data payload (232 bytes)
```

This layered design allows Skyfall to reuse the HC-12 driver's radio communication, addressing, filtering, acknowledgment, and CRC functionality while adding higher-level features.

## Features
**Skyfall-protocol** supports plenty of features. It provides a higher-level interface for secure and reliable communication, extending the underlying *HC-12 radio driver* with:

- **Encrypted messages** - Transmit text messages securely using XOR encryption with a unique encryption key assigned to each destination device.  
- **Encrypted file transfer** - Transfer files securely by splitting them into chunks of up to 232 bytes, encrypting each chunk, and transmitting them sequentially with acknowledgment.  
- **Reliable transmission** - Every Skyfall packet is passed through the HC-12 driver's reliable transport mechanism and must be successfully acknowledged before transmission is considered successful.  
- **Message and file support** - Supports both text messages and file transfers using dedicated message type identifiers.  
- **Packet chunking** - Files are automatically divided into 232-byte chunks. Each chunk has its own identifier, while the final chunk is marked with an end-of-file flag.  
- **Device-specific encryption keys** - Encryption keys are stored per destination device ID, allowing different IoT devices to use their own unique keys.  
- **Incoming message decryption** - Automatically detects encrypted packets, selects the encryption key associated with the sender, decrypts the payload, and returns the original data.  
- **Packet validation** - Validates message types, encryption types, control flags, and minimum packet size before processing incoming data.  
- **Multiple IoT clients** - Maintains independent file handlers for different sender IDs, allowing files from multiple IoT devices to be received and stored simultaneously.  
- **Direct file storage** - Incoming file chunks are written directly to storage as they are received, without requiring the entire file to be held in memory.  
- **Message callback** - Provides a callback mechanism for processing received text messages and completed file transfers.  
- **Configurable file naming** -Received files are automatically stored using a configurable prefix, sender ID, and file extension.  
- **UART timeout** - The receiver can continuously process incoming packets until the UART remains inactive for the configured timeout period.  

[**Skyfall protocol**](skyfall.py) designed to work with *MicroPython-compatible microcontrollers* such as *Raspberry Pi Pico* and *ESP32* while using the *HC-12 radio driver* as the underlying communication layer.

## Usage on microcontrollers
To use the **RadioHC12** and **Skyfall** classes on microcontrollers, establish point-to-point wireless communication to send secure messages and perform file transfers between several IoT devices.

### HC-12 radio messages
The **RadioHC12** class provides reliable, ACK-verified data packet transmission. Devices are assigned specific IDs, and filters can be set to ensure communication only happens within authorized radio groups.

#### Radio client
The *client node* sends message to a designated server and waits for the confirmation (ACK).

```Python
import time
from radio import RadioHC12

# ESP32 device
client_radio = RadioHC12(
    uart_id=1, 
    tx=17, 
    rx=18, 
    baudrate=9600, 
    my_id=2, # client ID, Role: IoT sensor
    allowed_devices=[1] # server ID = 1, our radio group
)

while True:
    message_str = "Hello server 1"
    payload_bytes = message_str.encode('utf-8')
    
    print("Sending reliable block to ServerID 1...")
    
    delivery_success = client_radio.send_reliable_block(dst_id=1, 
                                                        block=payload_bytes, 
                                                        max_retries=5)
    
    if delivery_success:
        print("[Success] Verified by Server 1 ACK!")
    else:
        print("[Error] Server 1 did not respond or frame was blocked.")

    time.sleep_ms(4000)

```
Code above repiditly send `"Hello server 1"` every 4 seconds using HC-12 radio.

#### Radio server
The *Radio server* continuously listens for incoming blocks, automatically validating sender-matching rules, handling ACK generation, and displaying incoming messages in the console.

```Python
import time
from radio import RadioHC12

# Raspberry Pi Pico device
server_radio = RadioHC12(
    uart_id=1, 
    tx=4, 
    rx=5, 
    baudrate=9600, 
    my_id=1, # server ID, Role: Server
    allowed_devices=[2, 3] # client IDs = [2, 3], our radio group
)

while True:
    result = server_radio.receive_reliable_block()
    
    if result is not None:
        sender_id, incoming_payload = result
        try:
            decoded_message = incoming_payload.decode('utf-8')
            print(f"[MESSAGE] From Node ID {sender_id}: '{decoded_message}'")
        except:
            pass
            
    time.sleep_ms(20)

```
The code above displays each incoming message along with the Node ID of the node from which it was received.

### Skyfall file transfer
The *Skyfall protocol* adds a security abstraction layer over **RadioHC12**. It allows encrypted and chunk-verified transmission of files (e.g., camera images) using pre-shared symmetric keys.

#### Skyfall client
The client encrypts and streams the file stream chunk-by-chunk to the remote destination IoT server (device).

```Python
import time
from radio import RadioHC12
from skyfall import Skyfall

# ESP32 device
client_radio = RadioHC12(
    uart_id=1, 
    tx=17, 
    rx=18, 
    baudrate=9600, 
    my_id=2, # client ID, Role: IoT sensor with camera
    allowed_devices=[1] # server ID = 1, our radio group
)

client_keys = {
    1: b"6a7d6b5c-5814-83eb-983f-29b3dc953fde"
}

protocol = Skyfall(radio_instance=client_radio, 
                   encryption_keys=client_keys)

while True:  
    print("Sending file to ServerID 1...")
    
    delivery_success = protocol.broadcast_secured_file(
                        dst_id=1, filename='img_buffer.png')
    
    if delivery_success:
        print("[Success] File transfered!")
    else:
        print("[Error] Server 1.")

    time.sleep_ms(60000)
```
In the code above, the file `img_buffer.png` is transmitted to the server with ID 1 every 60 seconds.

#### Skyfall server
The server tracks incoming secure packets, decrypts the received chunks, saves them to local storage, and notifies the main code that the file has been received using the `on_message` callback.

```Python
import time
from radio import RadioHC12
from skyfall import Skyfall

# Raspberry Pi Pico device
server_radio = RadioHC12(
    uart_id=1, 
    tx=4, 
    rx=5, 
    baudrate=9600, 
    my_id=1, # server ID, Role: Server
    allowed_devices=[2, 3] # client IDs = [2, 3], our radio group
)

server_keys  = {
    2: b"6a7d6b5c-5814-83eb-983f-29b3dc953fde",
    3: b"e8edcbad-9ec0-4686-aca0-d4d884222757"
}

protocol = Skyfall(radio_instance=server_radio, 
                   encryption_keys=server_keys)

def protocol_receiver_callback(msg_type, value):
    incoming_queue.append((msg_type, value))

incoming_queue = []

while True:
    # Listening to radio
    try:
        if server_radio.uart.any() != 0:
            protocol.read_secured_packages(file_prefix='radio_file_',
                                file_ext='png',
                                on_message=protocol_receiver_callback,
                                uart_timeout=5000)
    except: pass
    time.sleep_ms(5)

    # Executing queue 
    while len(incoming_queue) > 0:
        msg_type, msg_val = incoming_queue.pop(0)
        print(f'[RadiO] we have receieved: {msg_type}: {msg_val}')
            
    time.sleep_ms(20)
```
In the code above, `incoming_queue` is processed in the main loop, executing each message or file separately. In this example, messages are displayed in the console.

The examples mentioned above, along with their supporting configurations for microcontrollers such as the Raspberry Pi Pico and ESP32 running MicroPython, can be found in the nested [Code examples](/examples) folder.

## What to build over

By leveraging the **Skyfall protocol** and the **HC-12 radio driver**, you can engineer a diverse ecosystem of secure, long-range IoT solutions. This architecture combines reliable messages/files transmission with robust protocol-layer encryption, making it ideal for deployments where data integrity and privacy are paramount. 

It intended to be used across a wide range of environments, from **smart agriculture and greenhouse automation** to **perimeter security networks** for yards and farms. Whether you are tracking real-time environmental metrics or streaming encrypted images from remote camera nodes, the *Skyfall protocol* ensures that data remains safe from external tampering **[DO NOT FORGET to replace encryption keys in your code]**.

The synergy between resilient, long-range radio hardware and a secure protocol removes traditional infrastructure limits **where the traditional internet or Wifi are not available**.

[HC-12 radio basefarm IoT client/server example](https://medium.com/@dmytrosazonov/iot-how-to-stay-connected-when-others-dont-with-hc-12-radio-4e8100011cc5)

## Get in touch
Questions? Feel free to message me on Twitter:
https://twitter.com/dmytro_sazonov