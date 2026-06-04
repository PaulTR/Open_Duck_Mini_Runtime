import sounddevice as sd
import numpy as np

def run_audio_test():
    # --- CONFIGURATION ---
    DURATION = 5        # Seconds to record
    FS = 44100          # Sample rate
    
    # Based on your output:
    # Index 0 is the Mic (USB PnP Sound Device)
    # Index 1 is the Speaker (MAX98357A)
    MIC_INDEX = 0
    SPEAKER_INDEX = 1

    print(f"[*] Starting test...")
    print(f"[*] Recording for {DURATION} seconds... Speak into the USB Mic!")
    
    try:
        # 1. Record (Mono)
        # We explicitly use device=0
        recording = sd.rec(int(DURATION * FS), 
                           samplerate=FS, 
                           channels=1, 
                           device=MIC_INDEX)
        
        sd.wait() # Wait for recording to finish
        print("[+] Recording complete.")

        # 2. Process
        # Double the mono signal into stereo for the MAX98357A
        stereo_recording = np.tile(recording, (1, 2))
        
        # Optional: Boost volume by 2x if it's too quiet
        stereo_recording = stereo_recording * 2.0

        # 3. Playback
        print(f"[*] Playing back through Speaker (Index {SPEAKER_INDEX})...")
        sd.play(stereo_recording, FS, device=SPEAKER_INDEX)
        sd.wait()
        print("[+] Playback finished.")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    run_audio_test()
