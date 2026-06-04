from flask import Flask, request, jsonify
from flask_cors import CORS
from mini_bdx_runtime.duck_config import DuckConfig
from mini_bdx_runtime.rustypot_position_hwi import HWI
from gpiozero import LED, AngularServo
import time

app = Flask(__name__)
CORS(app)

print("Initializing Duck robot...")
duck_config = DuckConfig()
hwi = HWI(duck_config=duck_config)
motor_ids = [30, 31, 32, 33]
try:
    hwi.io.set_kps(motor_ids, [hwi.low_torque_kps[0]] * len(motor_ids))
except AttributeError:
    # If low_torque_kps doesn't exist on older APIs
    pass
print("Hardware connected successfully!")

# Setup Lights (GPIO 23 is Physical Pin 16, GPIO 24 is Physical Pin 18)
led1 = LED(23)
led2 = LED(24)

# Setup Antennas (SG90 Servos on D12/Pin32 and D13/Pin33)
servo_left = AngularServo(12, min_angle=-90, max_angle=90)
servo_right = AngularServo(13, min_angle=-90, max_angle=90)

antenna_angles = {
    'back': -90,
    'center': 0,
    'forward': 90
}

def set_lights(on):
    if on:
        led1.on()
        led2.on()
    else:
        led1.off()
        led2.off()

def set_antennas(antennas):
    if antennas:
        servo_left.angle = antenna_angles.get(antennas.get('left', 'center'), 0)
        servo_right.angle = antenna_angles.get(antennas.get('right', 'center'), 0)

@app.route('/read', methods=['GET'])
def read_position():
    try:
        position_list = hwi.io.read_present_position(motor_ids)
        positions = {}
        for i, mid in enumerate(motor_ids):
            positions[str(mid)] = position_list[i]
        return jsonify(positions)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/play', methods=['POST'])
def play_animation():
    data = request.json
    if not data or 'keyframes' not in data:
        return jsonify({"error": "No keyframes provided"}), 400
    
    keyframes = data['keyframes']
    
    try:
        try:
            initial_list = hwi.io.read_present_position(motor_ids)
            current_positions = {str(motor_ids[i]): initial_list[i] for i in range(len(motor_ids))}
        except Exception:
            current_positions = {}
            
        for frame in keyframes:
            set_lights(frame.get('lightsOn', False))
            set_antennas(frame.get('antennas', {}))
            
            motors = frame.get('motors', {})
            ids = [int(k) for k in motors.keys()]
            end_positions = list(motors.values())
            
            start_positions = [current_positions.get(str(mid), end_positions[j]) for j, mid in enumerate(ids)]
            
            dur = frame.get('durationMs', 500) / 1000.0
            interp = frame.get('interpolation', 'linear')
            
            steps = max(1, int(dur * 50))
            sleep_time = dur / steps
            
            for step in range(1, steps + 1):
                t = step / float(steps)
                if interp == 'bezier':
                    f = t * t * (3.0 - 2.0 * t)
                elif interp == 'bezier_viscous':
                    f = 1.0 - (1.0 - t)**3
                elif interp == 'bezier_clamped':
                    f = t**3
                else:
                    f = t
                    
                interp_positions = [start_positions[j] + (end_positions[j] - start_positions[j]) * f for j in range(len(ids))]
                if ids and interp_positions:
                    hwi.io.write_goal_position(ids, interp_positions)
                
                time.sleep(sleep_time)
                
            if ids and end_positions:
                hwi.io.write_goal_position(ids, end_positions)
                
            for j, mid in enumerate(ids):
                current_positions[str(mid)] = end_positions[j]
            
        # Turn off lights after sequence
        set_lights(False)
        set_antennas({'left': 'center', 'right': 'center'})
        hwi.io.disable_torque(motor_ids)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Run the server on all interfaces, port 5000
    app.run(host='0.0.0.0', port=5000)
