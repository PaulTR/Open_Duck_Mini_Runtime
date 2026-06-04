# Note: Save this file and run it from /home/duck/code/Open_Duck_Mini_Runtime/scripts
# using your 'duck' conda environment.

import sys
sys.path.append('..')

import time
from mini_bdx_runtime.duck_config import DuckConfig
from mini_bdx_runtime.rustypot_position_hwi import HWI
import RPi.GPIO as GPIO

print("Initializing Duck robot...")
duck_config = DuckConfig()
hwi = HWI(duck_config=duck_config)
print("Hardware connected successfully!")

# Set initial low torque for safety
motor_ids = [30, 31, 32, 33]
hwi.io.set_kps(motor_ids, [hwi.low_torque_kps[0]] * len(motor_ids))

# Setup Lights (Assuming BCM numbering for pins 16 and 18)
LIGHT_PINS = [16, 18]
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
for pin in LIGHT_PINS:
    GPIO.setup(pin, GPIO.OUT)

keyframes = [
    {
        "durationMs": 500,
        "motors": {
            "30": -0.3083,
            "31": -0.2408,
            "32": -0.0813,
            "33": -0.227
        },
        "lightsOn": False
    },
    {
        "durationMs": 500,
        "motors": {
            "30": -0.3099,
            "31": -0.2393,
            "32": -0.0752,
            "33": -0.5016
        },
        "lightsOn": False
    },
    {
        "durationMs": 500,
        "motors": {
            "30": -0.405,
            "31": -0.2408,
            "32": -0.0752,
            "33": 0.1411
        },
        "lightsOn": False
    }
]

def set_motors(motor_values):
    ids = [int(k) for k in motor_values.keys()]
    positions = list(motor_values.values())
    hwi.io.write_goal_position(ids, positions)

def set_lights(on):
    state = GPIO.HIGH if on else GPIO.LOW
    for pin in LIGHT_PINS:
        GPIO.output(pin, state)

print("Starting Head Animation...")
for i, frame in enumerate(keyframes):
    print(f"\nFrame {i+1}: Transitioning over {frame['durationMs']}ms, Lights: {'ON' if frame['lightsOn'] else 'OFF'}")
    set_lights(frame['lightsOn'])
    set_motors(frame['motors'])
    time.sleep(frame['durationMs'] / 1000.0)

print("\nAnimation Complete! Disabling torque...")
hwi.io.disable_torque(motor_ids)
# Turn off lights at the end
set_lights(False)
GPIO.cleanup()
