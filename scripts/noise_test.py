import serial
import time

# Configuration
SERIAL_PORT = '/dev/ttyACM0'
BAUDRATE = 1_000_000
SAMPLES_PER_MOTOR = 100 

# Your Duck's Motor Map
MOTOR_MAP = {
    "Right Leg": [10, 11, 12, 13, 14],
    "Left Leg":  [20, 21, 22, 23, 24],
    "Head/Neck": [30, 31, 32, 33]
}

def calculate_checksum(packet):
    return (~(sum(packet[2:]) & 0xFF)) & 0xFF

def send_ping(ser, motor_id):
    # Ping Packet: [Start1, Start2, ID, Length, Instruction, Checksum]
    packet = [0xFF, 0xFF, motor_id, 0x02, 0x01]
    packet.append(calculate_checksum(packet))
    
    ser.reset_input_buffer()
    ser.write(bytes(packet))
    
    start_time = time.time()
    response = ser.read(6) # Expected: FF FF ID LEN ERR CHK
    duration = (time.time() - start_time) * 1000 # in ms
    
    if len(response) == 6 and response[2] == motor_id:
        return True, duration
    return False, duration

def run_stress_test():
    print(f"--- Starting Full Duck Stress Test on {SERIAL_PORT} ---")
    print(f"Testing each motor {SAMPLES_PER_MOTOR} times...\n")

    try:
        ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=0.03)
    except Exception as e:
        print(f"Error: {e}")
        return

    print(f"{'Section':<12} | {'ID':<3} | {'Success %':<10} | {'Lat (ms)':<8} | {'Status'}")
    print("-" * 60)

    for section, ids in MOTOR_MAP.items():
        for m_id in ids:
            success_count = 0
            latencies = []
            
            for _ in range(SAMPLES_PER_MOTOR):
                success, lat = send_ping(ser, m_id)
                if success:
                    success_count += 1
                    latencies.append(lat)
                time.sleep(0.001) # Safety gap

            rate = (success_count / SAMPLES_PER_MOTOR) * 100
            avg_lat = sum(latencies)/len(latencies) if latencies else 0
            
            # Label the health
            if rate == 100: status = "OK"
            elif rate > 90: status = "NOISY"
            else: status = "BAD CABLE / FAILING"

            print(f"{section:<12} | {m_id:<3} | {rate:>8.1f}% | {avg_lat:>7.2f}  | {status}")
        print("-" * 60) # Divider between limbs

    ser.close()
    print("\nDiagnostic Complete.")

if __name__ == "__main__":
    run_stress_test()

