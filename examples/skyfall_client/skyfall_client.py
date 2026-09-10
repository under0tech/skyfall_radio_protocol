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
