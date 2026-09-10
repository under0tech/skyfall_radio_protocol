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
