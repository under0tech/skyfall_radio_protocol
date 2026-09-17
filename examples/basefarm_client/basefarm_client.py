import time

from machine import Pin
from radio import RadioHC12
from skyfall import Skyfall

RADIO_SERVER_ID = 1
PIR_PIN = 10
LED_PIN = 3

pir = Pin(PIR_PIN, Pin.IN)
led = Pin(LED_PIN, Pin.OUT)

# ESP32-C3 device
client_radio = RadioHC12(
    uart_id=1, 
    tx=21, 
    rx=20, 
    baudrate=9600, 
    my_id=3, # client ID, Role: IoT sensor no camera
    allowed_devices=[1] # server ID = 1, our radio group
)

client_keys = {
    1: b"e8edcbad-9ec0-4686-aca0-d4d884222757"
}

protocol = Skyfall(radio_instance=client_radio, 
                   encryption_keys=client_keys)

def pir_irq(pin):
    global pir_detected
    pir_detected = True

def pir_detection():
    print("Motion detected")

    led.on()
    protocol.broadcast_secured_message(
        dst_id=RADIO_SERVER_ID,
        message=f"Motion detected on north-west")
    led.off()
      
    time.sleep_ms(1000)

pir_detected = False
pir.irq(trigger=Pin.IRQ_RISING,
        handler=pir_irq)

led.off()

while True:  
    print('...')
    if pir_detected:
        time.sleep_ms(500)
        pir_detection()
        pir_detected = False

    time.sleep_ms(500)
