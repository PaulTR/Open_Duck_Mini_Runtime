import serial
import time

PORT = '/dev/ttyACM0'
BAUD = 1_000_000

def clear():
    print(f"Opening {PORT} to purge buffers...")
    try:
        # Open with a long timeout to ensure we grab everything
        ser = serial.Serial(PORT, BAUD, timeout=1)
        
        # 1. Flush the OS buffers
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        
        # 2. Read anything that might be lingering
        time.sleep(0.1)
        if ser.in_waiting > 0:
            garbage = ser.read(ser.in_waiting)
            print(f"Purged {len(garbage)} bytes of garbage data.")
            
        # 3. Reset Status Return Level (Standard for Open Duck)
        # This ensures motors talk back exactly when the library expects them to
        # Packet: ID 254, Length 4, Write, Addr 0x13, Val 0x02, Checksum
        print("Resetting motors to Status Level 2...")
        ser.write(bytes([0xFF, 0xFF, 0xFE, 0x04, 0x03, 0x13, 0x02, 0xE8]))
        
        ser.close()
        print("Bus cleared. Rustypot should be happy now.")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    clear()

