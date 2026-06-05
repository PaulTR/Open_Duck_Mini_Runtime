import serial
import time

SERIAL_PORT = '/dev/ttyACM0' 
BAUDRATE = 1_000_000

def scan():
    try:
        ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=0.05)
        print(f"Scanning for motors on {SERIAL_PORT}...")
        found_motors = []

        # Typically Open Duck Mini uses IDs 1 through 10 or 12
        for motor_id in range(1, 15):
            # Ping Packet for STS3215: [0xFF, 0xFF, ID, 0x02, 0x01, Checksum]
            checksum = ~(motor_id + 0x02 + 0x01) & 0xFF
            packet = bytes([0xFF, 0xFF, motor_id, 0x02, 0x01, checksum])
            
            ser.write(packet)
            reply = ser.read(6) # Expecting 6 bytes back
            
            if reply:
                print(f"  [+] Motor ID {motor_id:02d}: DETECTED")
                found_motors.append(motor_id)
            else:
                # No response
                pass
        
        ser.close()
        
        if not found_motors:
            print("\nRESULT: No motors detected at all! Check your battery and main power cable.")
        else:
            print(f"\nRESULT: Found {len(found_motors)} motors: {found_motors}")
            print("If you are missing IDs (e.g., 1, 2, 4 but 3 is missing), check the cable to that motor.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    scan()
