import logging
import datetime
import time
import pickle
import numpy as np
import os
import subprocess  # For torque release via turn_off.py

from mini_bdx_runtime.rustypot_position_hwi import HWI
from mini_bdx_runtime.onnx_infer import OnnxInfer
from mini_bdx_runtime.raw_imu import Imu
from mini_bdx_runtime.poly_reference_motion import PolyReferenceMotion
from mini_bdx_runtime.xbox_controller import XBoxController
from mini_bdx_runtime.feet_contacts import FeetContacts
from mini_bdx_runtime.eyes import Eyes
from mini_bdx_runtime.sounds import Sounds
from mini_bdx_runtime.antennas import Antennas
from mini_bdx_runtime.projector import Projector  # The class you provided
from mini_bdx_runtime.rl_utils import make_action_dict, LowPassActionFilter
from mini_bdx_runtime.duck_config import DuckConfig

# Configure logging
logging.basicConfig(
    filename='duck_io_errors.log',
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

HOME_DIR = os.path.expanduser("~")

class RLWalk:
    def __init__(
        self,
        onnx_model_path: str,
        duck_config_path: str = f"{HOME_DIR}/duck_config.json",
        serial_port: str = "/dev/ttyACM0",
        control_freq: float = 50,
        pid=[30, 0, 0],
        action_scale=0.25,
        commands=False,
        pitch_bias=0,
        save_obs=False,
        replay_obs=None,
        cutoff_frequency=None,
    ):
        self.duck_config = DuckConfig(config_json_path=duck_config_path)
        self.commands = commands
        self.pitch_bias = pitch_bias
        self.onnx_model_path = onnx_model_path
        self.policy = OnnxInfer(self.onnx_model_path, awd=True)

        self.num_dofs = 14
        self.control_freq = control_freq
        self.pid = pid

        self.save_obs = save_obs
        if self.save_obs:
            self.saved_obs = []

        self.replay_obs = replay_obs
        if self.replay_obs is not None:
            self.replay_obs = pickle.load(open(self.replay_obs, "rb"))

        self.action_filter = None
        if cutoff_frequency is not None:
            self.action_filter = LowPassActionFilter(self.control_freq, cutoff_frequency)

        self.hwi = HWI(self.duck_config, serial_port)
        self.start()

        self.imu = Imu(
            sampling_freq=int(self.control_freq),
            user_pitch_bias=self.pitch_bias,
            upside_down=self.duck_config.imu_upside_down,
        )

        self.feet_contacts = FeetContacts()
        self.action_scale = action_scale
        self.last_action = np.zeros(self.num_dofs)
        self.last_last_action = np.zeros(self.num_dofs)
        self.last_last_last_action = np.zeros(self.num_dofs)

        self.init_pos = list(self.hwi.init_pos.values())
        self.motor_targets = np.array(self.init_pos.copy())
        self.prev_motor_targets = np.array(self.init_pos.copy())
        self.last_commands = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        self.paused = self.duck_config.start_paused

        if self.commands:
            self.xbox_controller = XBoxController(20)

        self.PRM = PolyReferenceMotion("./polynomial_coefficients.pkl")
        self.imitation_i = 0
        self.imitation_phase = np.array([0, 0])
        self.phase_frequency_factor = 1.0
        self.phase_frequency_factor_offset = self.duck_config.phase_frequency_factor_offset

        # Hardware Initialization based on config
        self.eyes = Eyes() if self.duck_config.eyes else None
        
        self.projector = None
        if self.duck_config.projector:
            try:
                self.projector = Projector()
                print("Projector Initialized")
            except Exception as e:
                print(f"Projector initialization failed: {e}")

        self.sounds = Sounds(volume=1.0, sound_directory="../mini_bdx_runtime/assets/") if self.duck_config.speaker else None
        self.antennas = Antennas() if self.duck_config.antennas else None

    def get_obs(self):
        imu_data = self.imu.get_data()
        dof_pos = self.hwi.get_present_positions(ignore=["left_antenna", "right_antenna"])
        dof_vel = self.hwi.get_present_velocities(ignore=["left_antenna", "right_antenna"])

        if dof_pos is None or dof_vel is None: return None
        if len(dof_pos) != self.num_dofs or len(dof_vel) != self.num_dofs: return None

        obs = np.concatenate([
            imu_data["gyro"], imu_data["accelero"], self.last_commands,
            dof_pos - self.init_pos, dof_vel * 0.05,
            self.last_action, self.last_last_action, self.last_last_last_action,
            self.motor_targets, self.feet_contacts.get(), self.imitation_phase,
        ])
        return obs

    def start(self):
        kps = [self.pid[0]] * 14
        kds = [self.pid[2]] * 14
        kps[5:9] = [8, 8, 8, 8]
        self.hwi.set_kps(kps)
        self.hwi.set_kds(kds)
        time.sleep(0.2)
        all_joints = list(self.hwi.joints.keys())
        current_command = {name: 0.0 for name in all_joints}
        groups = [
            ["right_hip_yaw", "right_hip_roll", "right_hip_pitch", "right_knee", "right_ankle"],
            ["left_hip_yaw", "left_hip_roll", "left_hip_pitch", "left_knee", "left_ankle"],
            ["neck_pitch", "head_pitch", "head_yaw", "head_roll"]
        ]
        for group in groups:
            for name in group:
                if name in self.hwi.init_pos: current_command[name] = self.hwi.init_pos[name]
            try:
                self.hwi.set_position_all(current_command)
                time.sleep(0.4)
            except Exception as e: print(f"Warning: {e}")
        self.hwi.set_position_all(self.hwi.init_pos)
        time.sleep(0.5)
        print("Startup complete.")

    def run(self):
        i = 0
        try:
            print("Starting")
            start_t = time.time()
            while True:
                t = time.time()
                if self.commands:
                    self.last_commands, self.buttons, lt, rt = self.xbox_controller.get_last_command()
                    
                    if self.buttons.dpad_up.triggered: self.phase_frequency_factor_offset += 0.05
                    if self.buttons.dpad_down.triggered: self.phase_frequency_factor_offset -= 0.05
                    self.phase_frequency_factor = 1.3 if self.buttons.LB.is_pressed else 1.0

                    # X button toggles projector
                    if self.buttons.X.triggered:
                        if self.projector:
                            self.projector.switch()

                    if self.buttons.B.triggered and self.sounds:
                        self.sounds.play_random_sound()

                    if self.antennas:
                        self.antennas.set_position_left(rt)
                        self.antennas.set_position_right(lt)

                    if self.buttons.A.triggered:
                        self.paused = not self.paused
                        print("PAUSE" if self.paused else "UNPAUSE")

                if self.paused:
                    time.sleep(0.1)
                    continue

                obs = self.get_obs()
                if obs is None: continue

                self.imitation_i += 1 * (self.phase_frequency_factor + self.phase_frequency_factor_offset)
                self.imitation_i = self.imitation_i % self.PRM.nb_steps_in_period
                self.imitation_phase = np.array([
                    np.cos(self.imitation_i / self.PRM.nb_steps_in_period * 2 * np.pi),
                    np.sin(self.imitation_i / self.PRM.nb_steps_in_period * 2 * np.pi),
                ])

                action = self.policy.infer(obs)
                self.last_last_last_action, self.last_last_action = self.last_last_action.copy(), self.last_action.copy()
                self.last_action = action.copy()

                self.motor_targets = self.init_pos + action * self.action_scale

                if self.action_filter is not None:
                    self.action_filter.push(self.motor_targets)
                    if (time.time() - start_t > 1):
                        self.motor_targets = self.action_filter.get_filtered_action()

                self.prev_motor_targets = self.motor_targets.copy()
                self.motor_targets[5:9] += self.last_commands[3:]

                try:
                    self.hwi.set_position_all(make_action_dict(self.motor_targets, list(self.hwi.joints.keys())))
                except OSError as e:
                    logging.error(f"IO Error: {e}")

                i += 1
                took = time.time() - t
                sleep_time = max(0, 1 / self.control_freq - took)
                time.sleep(sleep_time)

        except KeyboardInterrupt:
            print("\nShutting down...")
            if self.antennas: self.antennas.stop()
            if self.eyes: self.eyes.stop()
            if self.projector: self.projector.stop()
            self.feet_contacts.stop()
            
            # Use subprocess to run your torque release script
            script_dir = os.path.dirname(os.path.abspath(__file__))
            subprocess.run(["python3", "turn_off.py"], cwd=script_dir)
            print("Torque released. OFF")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--onnx_model_path", type=str, required=True)
    parser.add_argument("--duck_config_path", default=f"{HOME_DIR}/duck_config.json")
    parser.add_argument("-a", "--action_scale", type=float, default=0.25)
    parser.add_argument("-p", type=int, default=30)
    parser.add_argument("-i", type=int, default=0)
    parser.add_argument("-d", type=int, default=0)
    parser.add_argument("-c", "--control_freq", type=int, default=50)
    parser.add_argument("--pitch_bias", type=float, default=0)
    parser.add_argument("--commands", action="store_true", default=True)
    parser.add_argument("--save_obs", action="store_true", default=False)
    parser.add_argument("--replay_obs", default=None)
    parser.add_argument("--cutoff_frequency", type=float, default=None)

    args = parser.parse_args()
    rl_walk = RLWalk(args.onnx_model_path, args.duck_config_path, "/dev/ttyACM0", args.control_freq, [args.p, args.i, args.d], args.action_scale, args.commands, args.pitch_bias, args.save_obs, args.replay_obs, args.cutoff_frequency)
    rl_walk.run()
