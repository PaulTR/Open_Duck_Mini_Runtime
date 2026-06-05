import asyncio
import os
import sys
import json
import time
import pyaudio
import numpy as np
import soundfile as sf
from google import genai
from google.genai import types

# --- 1. HARDWARE SETUP (Exact copy from your script) ---
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

# --- 2. AUDIO BRIDGE CONFIG ---
FORMAT = pyaudio.paInt16
CHANNELS = 1
HW_SAMPLE_RATE = 48000
API_SEND_RATE = 16000
CHUNK_SIZE = 1024
MIC_FACTOR = 3 

pya = pyaudio.PyAudio()
audio_queue_mic = asyncio.Queue(maxsize=5)
audio_queue_output = asyncio.Queue() # Shared queue for Gemini and Local Sounds

# Hardware Helper Functions
def set_lights(on):
    if on: led1.on(); led2.on()
    else: led1.off(); led2.off()

def set_projector(on):
    if on: projector.on()
    else: projector.off()

def set_antennas(positions):
    def get_angle(p): return -90 if p == 'back' else 90 if p == 'forward' else 0
    servo_left.angle = get_angle(positions.get('left', 'center'))
    servo_right.angle = get_angle(positions.get('right', 'center'))

def bezier_interpolate(t, type_str):
    if type_str == 'linear': return t
    if type_str in ['bezier', 'bezier_viscous', 'bezier_clamped']:
        return t * t * (3.0 - 2.0 * t)
    return t

def play_animation_task(action_name):
    """Wrapper to run the blocking animation logic in a thread."""
    try:
        json_path = f"assets/{action_name}.json"
        print(f"ROBOT ACTION: {action_name}")
        
        if not os.path.exists(json_path): return
        with open(json_path, 'r') as f:
            data = json.load(f)
        
        # --- 1. HANDLE AUDIO (Push to shared queue to avoid ALSA conflict) ---
        global_sound = data.get('globalSound', '')
        if global_sound:
            sound_path = f"assets/{global_sound}"
            if os.path.exists(sound_path):
                with sf.SoundFile(sound_path) as s_file:
                    audio_data = s_file.read(dtype='int16')
                    # Convert to mono if stereo
                    if s_file.channels > 1:
                        audio_data = audio_data.mean(axis=1).astype(np.int16)
                    # Resample to 48k for the speaker task
                    if s_file.samplerate == 24000:
                        audio_data = np.repeat(audio_data, 2)
                    elif s_file.samplerate == 16000:
                        audio_data = np.repeat(audio_data, 3)
                    # Push bytes to the active speaker task
                    audio_queue_output.put_nowait(audio_data.tobytes())

        # --- 2. HANDLE MOTORS ---
        keyframes = data.get('keyframes', [])
        try:
            start_pos = hwi.io.read_present_position(motor_ids)
            current_pos = {str(mid): pos for mid, pos in zip(motor_ids, start_pos)}
            hwi.io.enable_torque(motor_ids)
        except: current_pos = {str(mid): 0 for mid in motor_ids}

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

    except Exception as e:
        print(f"Animation Error: {e}")

# --- 3. GEMINI API CONFIG ---
api_key = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key, http_options={'api_version': 'v1alpha'})

live_config = types.LiveConnectConfig(
    response_modalities=["AUDIO"],
    system_instruction=types.Content(
        parts=[types.Part(text=(
            "You are a physical robot. Do not speak. Respond ONLY using tools. "
            "Use 'trigger_action' with action_name='yes', 'no', or 'beep1'."
        ))]
    ),
    tools=[types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="trigger_action",
                description="Triggers a physical robot animation.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "action_name": types.Schema(type="STRING", description="Action name like 'yes' or 'beep1'")
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
            # 1. Handle Tools
            if response.tool_call:
                for call in response.tool_call.function_calls:
                    if call.name == "trigger_action":
                        action = call.args.get("action_name")
                        # Run animation/audio logic in background thread
                        asyncio.create_task(asyncio.to_thread(play_animation_task, action))
                    
                    # Fix Deprecation: use send_tool_response
                    await session.send_tool_response(
                        function_responses=[types.FunctionResponse(
                            id=call.id, name=call.name, response={"status": "ok"}
                        )]
                    )
            
            # 2. Handle Text Transcriptions
            sc = response.server_content
            if sc and sc.input_transcription:
                print(f"You: {sc.input_transcription.text}")

async def play_audio():
    """Single speaker task for ALL audio (Gemini voice + Local wavs)"""
    stream = await asyncio.to_thread(
        pya.open, format=FORMAT, channels=CHANNELS, rate=HW_SAMPLE_RATE,
        output=True, output_device_index=SPEAKER_INDEX
    )
    while True:
        bytestream = await audio_queue_output.get()
        await asyncio.to_thread(stream.write, bytestream)

async def run():
    try:
        async with client.aio.live.connect(
            model="gemini-3.1-flash-live-preview", config=live_config
        ) as live_session:
            print("Robot Online. I am listening...")
            async with asyncio.TaskGroup() as tg:
                tg.create_task(send_realtime(live_session))
                tg.create_task(listen_audio())
                tg.create_task(receive_and_trigger(live_session))
                tg.create_task(play_audio())
    except Exception as e:
        print(f"Session Error: {e}")
    finally:
        pya.terminate()

if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
