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
