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
