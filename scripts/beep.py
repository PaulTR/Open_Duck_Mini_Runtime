import asyncio
import os
import sys
import json
import time
import pyaudio
import numpy as np
import sounddevice as sd
import soundfile as sf
from google import genai
from google.genai import types

# --- 1. HARDWARE SETUP (Exact copy from your working script) ---
from mini_bdx_runtime.duck_config import DuckConfig
from mini_bdx_runtime.rustypot_position_hwi import HWI
from gpiozero import LED, AngularServo

config_hw = DuckConfig()
hwi = HWI(config_hw)
motor_ids = [30, 31, 32, 33]
MIC_INDEX = 1      
SPEAKER_INDEX = 0  

led1, led2, projector = LED(23), LED(24), LED(25)
servo_left = AngularServo(12, min_angle=-90, max_angle=90)
servo_right = AngularServo(13, min_angle=-90, max_angle=90)

# Hardware Helper Functions
def set_lights(on):
    if on: led1.on(); led2.on()
    else: led1.off(); led2.off()

def set_projector(on):
    if on: projector.on()
    else: projector.off()

def get_antenna_angle(pos_str):
    if pos_str == 'back': return -90
    if pos_str == 'forward': return 90
    return 0

def set_antennas(positions):
    servo_left.angle = get_antenna_angle(positions.get('left', 'center'))
    servo_right.angle = get_antenna_angle(positions.get('right', 'center'))

def bezier_interpolate(t, type_str):
    if type_str == 'linear': return t
    if type_str in ['bezier', 'bezier_viscous', 'bezier_clamped']:
        return t * t * (3.0 - 2.0 * t)
    return t

def play_animation_safe(action_name):
    """Wrapper to map action_name to file path and run safely."""
    try:
        json_path = f"assets/{action_name}.json"
        print(f"ROBOT ACTION: {action_name}")
        play_animation(json_path)
    except Exception as e:
        print(f"Animation Error: {e}")

def play_animation(json_file_path):
    if not os.path.exists(json_file_path): 
        print(f"File not found: {json_file_path}")
        return
    with open(json_file_path, 'r') as f:
        data = json.load(f)
    keyframes = data.get('keyframes', [])
    global_sound = data.get('globalSound', '')
    
    if global_sound:
        try:
            sound_path = f"assets/{global_sound}"
            if os.path.exists(sound_path):
                audio_data, fs = sf.read(sound_path, dtype='float32')
                if len(audio_data.shape) == 1:
                    audio_data = np.tile(audio_data.reshape(-1, 1), (1, 2))
                sd.play(audio_data * 2.0, fs, device=SPEAKER_INDEX)
        except Exception: pass

    try:
        start_pos = hwi.io.read_present_position(motor_ids)
        current_pos = {str(mid): pos for mid, pos in zip(motor_ids, start_pos)}
        hwi.io.enable_torque(motor_ids)
    except:
        current_pos = {str(mid): 0 for mid in motor_ids}

    for frame in keyframes:
        set_lights(frame.get('lightsOn', False))
        set_projector(frame.get('projectorOn', False))
        set_antennas(frame.get('antennas', {}))
        dur = frame.get('durationMs', 1000) / 1000.0
        steps = max(1, int(dur * 30))
        target_motors = frame.get('motors', {})
        start_frame_pos = current_pos.copy()
        start_t = time.time()
        for step in range(1, steps + 1):
            t = step / float(steps)
            eased_t = bezier_interpolate(t, frame.get('interpolation', 'linear'))
            step_targets = []
            for mid in motor_ids:
                s_val = start_frame_pos.get(str(mid), 0)
                e_val = target_motors.get(str(mid), s_val)
                val = s_val + (e_val - s_val) * eased_t
                step_targets.append(float(val))
                current_pos[str(mid)] = val
            try: hwi.io.write_goal_position(motor_ids, step_targets)
            except: pass
            target_t = start_t + step * (dur / steps)
            now = time.time()
            if target_t > now: time.sleep(target_t - now)
    
    set_lights(False); set_projector(False); set_antennas({'left': 'center', 'right': 'center'})
    try: hwi.io.disable_torque(motor_ids)
    except: pass

# --- 2. AUDIO BRIDGE (48kHz Hardware -> 16kHz API) ---
FORMAT = pyaudio.paInt16
CHANNELS = 1
HW_SAMPLE_RATE = 48000
API_SEND_RATE = 16000
CHUNK_SIZE = 1024
MIC_FACTOR = 3 

pya = pyaudio.PyAudio()
audio_queue_mic = asyncio.Queue(maxsize=5)

# --- 3. GEMINI API CONFIG ---
api_key = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key, http_options={'api_version': 'v1alpha'})

# CONSOLIDATED CONFIG: Single tool with a parameter
live_config = types.LiveConnectConfig(
    response_modalities=["AUDIO"],
    system_instruction=types.Content(
        parts=[types.Part(text=(
            "You are a physical robot. Do not speak. Respond ONLY using tools. "
            "Use the 'trigger_action' tool with 'yes' if you agree, 'no' if you disagree, or if the user says something that isnt a yes or no question, use 'beep1'"
        ))]
    ),
    tools=[types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="trigger_action",
                description="Triggers a physical robot animation based on user input.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "action_name": types.Schema(
                            type="STRING", 
                            description="The name of the action: 'yes', 'no', 'beep1'."
                        )
                    },
                    required=["action_name"]
                )
            )
        ]
    )]
)

# --- 4. ASYNC TASKS ---

async def listen_audio():
    stream = await asyncio.to_thread(
        pya.open, format=FORMAT, channels=CHANNELS, rate=HW_SAMPLE_RATE,
        input=True, input_device_index=MIC_INDEX, frames_per_buffer=CHUNK_SIZE * MIC_FACTOR
    )
    while True:
        data = await asyncio.to_thread(stream.read, CHUNK_SIZE * MIC_FACTOR, exception_on_overflow=False)
        audio_array = np.frombuffer(data, dtype=np.int16)
        resampled = audio_array[::MIC_FACTOR].tobytes()
        await audio_queue_mic.put({"data": resampled, "mime_type": "audio/pcm"})

async def send_realtime(session):
    while True:
        msg = await audio_queue_mic.get()
        await session.send_realtime_input(audio=msg)

async def receive_and_trigger(session):
    while True:
        turn = session.receive()
        async for response in turn:
            if response.tool_call:
                for call in response.tool_call.function_calls:
                    if call.name == "trigger_action":
                        action = call.args.get("action_name")
                        # Launch animation thread
                        asyncio.create_task(asyncio.to_thread(play_animation_safe, action))
                    
                    # Acknowledge the call
                    await session.send(input={
                        "function_responses": [{
                            "id": call.id, "name": call.name, "response": {"status": "ok"}
                        }]
                    })
            
            sc = response.server_content
            if sc and sc.input_transcription:
                print(f"You said: {sc.input_transcription.text}")

async def run():
    try:
        async with client.aio.live.connect(
            model="gemini-3.1-flash-live-preview", 
            config=live_config
        ) as live_session:
            print("Robot Online. Consolidated Tool Mode Active.")
            async with asyncio.TaskGroup() as tg:
                tg.create_task(send_realtime(live_session))
                tg.create_task(listen_audio())
                tg.create_task(receive_and_trigger(live_session))
    except Exception as e:
        print(f"Session Error: {e}")
    finally:
        pya.terminate()

if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\nShutting down.")
