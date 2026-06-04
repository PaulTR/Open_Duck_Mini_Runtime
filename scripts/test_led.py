from gpiozero import LED
from time import sleep

# GPIO 23 is Physical Pin 16, GPIO 24 is Physical Pin 18
led1 = LED(23)
led2 = LED(24)
projector = LED(25)

while True:
    led1.on()
    led2.on()
    projector.on()
    sleep(1)
    led1.off()
    led2.off()
    projector.off()
    sleep(1)
