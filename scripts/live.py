import asyncio
import os
import sys
import pyaudio
import numpy as np
from google import genai
from gpiozero import LED, AngularServo
from mini_bdx_runtime.duck_config import DuckConfig
from mini_bdx_runtime.rustypot_position_hwi import HWI

# --- 1. HARDWARE SETUP (Exact copy from your working script) ---
config_hw = DuckConfig()
hwi = HWI(config_hw)
motor_ids = [30, 31, 32, 33]

MIC_INDEX = 1      # USB PnP
SPEAKER_INDEX = 0  # MAX98357A I2S

led1, led2, projector = LED(23), LED(24), LED(25)
servo_left = AngularServo(12, min_angle=-90, max_angle=90)
servo_right = AngularServo(13, min_angle=-90, max_angle=90)

# --- 2. AUDIO CONFIGURATION ---
FORMAT = pyaudio.paInt16
CHANNELS = 1
HW_SAMPLE_RATE = 48000
API_SEND_RATE = 16000
API_RECV_RATE = 24000
CHUNK_SIZE = 1024

# Factors for 48kHz bridge
MIC_FACTOR = 3 
SPK_FACTOR = 2

pya = pyaudio.PyAudio()
audio_queue_output = asyncio.Queue()
audio_queue_mic = asyncio.Queue(maxsize=5)

# --- 3. GEMINI CONFIG ---
api_key = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key, http_options={'api_version': 'v1alpha'})

MODEL = "gemini-3.1-flash-live-preview"
CONFIG = {
    "response_modalities": ["AUDIO"],
    "system_instruction": "You are a friendly robot assistant. Respond concisely.",
    "output_audio_transcription": {},
    "input_audio_transcription": {},
}

# --- 4. ASYNC TASKS ---

async def listen_audio():
    """Listens at 48k, sends 16k to queue."""
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
    """Sends mic data to Gemini."""
    while True:
        msg = await audio_queue_mic.get()
        await session.send_realtime_input(audio=msg)

async def receive_audio(session):
    """Processes turns, audio chunks, and prints transcriptions."""
    while True:
        turn = session.receive()
        async for response in turn:
            sc = response.server_content
            if not sc:
                continue
            
            # Handle Audio Output
            if sc.model_turn:
                for part in sc.model_turn.parts:
                    if part.inline_data:
                        audio_queue_output.put_nowait(part.inline_data.data)
            
            # Handle Transcriptions (Terminal Debugging)
            if sc.output_transcription:
                print(f"Robot: {sc.output_transcription.text}", flush=True)
            if sc.input_transcription:
                print(f"You: {sc.input_transcription.text}", flush=True)

        # Clear output queue on turn end to prevent delayed audio
        while not audio_queue_output.empty():
            audio_queue_output.get_nowait()

async def play_audio():
    """Receives 24k, upsamples to 48k for I2S speaker."""
    stream = await asyncio.to_thread(
        pya.open, format=FORMAT, channels=CHANNELS, rate=HW_SAMPLE_RATE,
        output=True, output_device_index=SPEAKER_INDEX
    )
    while True:
        bytestream = await audio_queue_output.get()
        audio_array = np.frombuffer(bytestream, dtype=np.int16)
        resampled = np.repeat(audio_array, SPK_FACTOR).tobytes()
        await asyncio.to_thread(stream.write, resampled)

async def run():
    try:
        async with client.aio.live.connect(model=MODEL, config=CONFIG) as live_session:
            print("Connected to Gemini Live! Listening...")
            async with asyncio.TaskGroup() as tg:
                tg.create_task(send_realtime(live_session))
                tg.create_task(listen_audio())
                tg.create_task(receive_audio(live_session))
                tg.create_task(play_audio())
    except Exception as e:
        print(f"Connection closed/Error: {e}")
    finally:
        pya.terminate()

if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
