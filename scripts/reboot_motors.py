import time
from rustypot import Sts3215PyController

# Use the serial port defined in your duck_config.json
# Usually '/dev/ttyAMA0' on Pi Zero or '/dev/ttyUSB0' if using a USB adapter
SERIAL_PORT = '/dev/ttyAMA0' 
BAUDRATE = 1_000_000

print(f"Connecting to motors on {SERIAL_PORT}...")
try:
    c = Sts3215PyController(serial_port=SERIAL_PORT, baudrate=BAUDRATE, timeout=0.1)
    
    # ID 254 is the broadcast ID for Feetech/Dynamixel. 
    # Sending a reboot to 254 tells ALL motors on the bus to restart.
    print("Sending broadcast reboot command (ID 254)...")
    c.reboot(254)
    
    # It takes about 1-2 seconds for motors to cycle back online
    print("Waiting for motors to restart...")
    time.sleep(2.0)
    
    print("Reboot complete. You can now try running your walk script again.")
except Exception as e:
    print(f"Failed to communicate with the bus: {e}")
    print("If this fails, the serial port itself might be locked.")
