import serial
import time

# Configuration - /dev/ttyAMA0 is the default for Pi Zero 2W on Open Duck
SERIAL_PORT = '/dev/ttyACM0' 
BAUDRATE = 1_000_000

def reboot_motors():
    print(f"Connecting to {SERIAL_PORT}...")
    try:
        # Open serial connection
        ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=0.1)
        
        # STS3215 Reboot Packet (Broadcast ID 254)
        # Format: [Start, Start, ID, Length, Instruction, Checksum]
        # ID 0xFE (254) = Broadcast to all motors
        # Inst 0x08 = Reboot
        packet = bytes([0xFF, 0xFF, 0xFE, 0x02, 0x08, 0xF7])
        
        print("Sending broadcast reboot signal to all motors...")
        ser.write(packet)
        ser.flush()
        
        # Motors take about 1-2 seconds to cycle their internal firmware
        print("Done. Waiting 2 seconds for motors to cycle...")
        time.sleep(2.0)
        
        ser.close()
        print("Motors reset. You can now try v2_rl_walk_mujoco.py again.")
        
    except Exception as e:
        print(f"Error: {e}")
        print("Make sure no other scripts (like the walk script) are currently running.")

if __name__ == "__main__":
    reboot_motors()
