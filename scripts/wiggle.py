import time
import sys
try:
    from mini_bdx_runtime import rustypot
except ImportError:
    import rustypot # Fallback if linked differently

# --- Configuration ---
DEVICE = '/dev/ttyACM0'
BAUD_RATE = 1000000
MOTOR_ID = 10        # The ID for left_hip_yaw (change as needed)
WIGGLE_RAD = 0.087    # ~5 degrees in radians
CYCLES = 3            # How many times to wiggle
# ---------------------

def test_wiggle():
    print(f"--- Motor Wiggle Test (ID: {MOTOR_ID}) ---")
    
    try:
        # Initialize connection
        print(f"Connecting to {DEVICE} at {BAUD_RATE} baud...")
        io = rustypot.feetech(DEVICE, BAUD_RATE)
        
        # Try to read the initial position
        print(f"Reading initial position for motor {MOTOR_ID}...")
        positions = io.read_present_position([MOTOR_ID])
        
        if not positions:
            print(f"Error: Could not read motor {MOTOR_ID}. Check power and ID.")
            return
            
        start_pos = positions[0]
        print(f"Start Position: {start_pos:.3f} rad")

        # Perform the wiggle
        for i in range(CYCLES):
            print(f"  Wiggle {i+1}/{CYCLES}...")
            
            # Move Right
            io.write_goal_position([MOTOR_ID], [start_pos + WIGGLE_RAD])
            time.sleep(0.3)
            
            # Move Left
            io.write_goal_position([MOTOR_ID], [start_pos - WIGGLE_RAD])
            time.sleep(0.3)

        # Return to the starting position
        print("Returning to original position...")
        io.write_goal_position([MOTOR_ID], [start_pos])
        time.sleep(0.5)
        print("Test Complete!")

    except Exception as e:
        print(f"\nAn error occurred: {e}")
        print("\nTroubleshooting tips:")
        print(f"1. Check if the motor is powered (12V).")
        print(f"2. Ensure the USB-to-TTL adapter is at {DEVICE}.")
        print(f"3. Try running with 'sudo' if you get Permission Denied.")

if __name__ == "__main__":
    test_wiggle()
