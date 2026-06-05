import board
import digitalio
import time
import sys

# Pin setup
LEFT_FOOT_PIN = board.D22
RIGHT_FOOT_PIN = board.D27

class FeetContacts:
    def __init__(self):
        # Setup Left Foot
        self.left_foot = digitalio.DigitalInOut(LEFT_FOOT_PIN)
        self.left_foot.direction = digitalio.Direction.INPUT
        self.left_foot.pull = digitalio.Pull.UP

        # Setup Right Foot
        self.right_foot = digitalio.DigitalInOut(RIGHT_FOOT_PIN)
        self.right_foot.direction = digitalio.Direction.INPUT
        self.right_foot.pull = digitalio.Pull.UP

    def get_status(self):
        # Returns True if pressed (connected to GND)
        left = not self.left_foot.value
        right = not self.right_foot.value
        return left, right

    def stop(self):
        self.left_foot.deinit()
        self.right_foot.deinit()

if __name__ == "__main__":
    feet = FeetContacts()
    print("--- Foot Switch Calibration ---")
    print("Press Ctrl+C to exit.")
    print("Wiring: Pins 22/27 to switch, other side of switch to GND.")
    print("-" * 31)

    try:
        while True:
            left, right = feet.get_status()
            
            # Format the strings for easy reading
            l_str = "PRESSED" if left else "-------"
            r_str = "PRESSED" if right else "-------"
            
            # Print to the same line using carriage return \r
            sys.stdout.write(f"\rLEFT (22): {l_str} | RIGHT (27): {r_str}")
            sys.stdout.flush()
            
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\n\nExiting...")
    finally:
        feet.stop()
