import os
import cv2
import subprocess

print("Initializing camera via system call...")

# Temporary file to hold the raw capture
temp_raw_path = "/home/duck/code/Open_Duck_Mini_Runtime/scripts/temp_raw.jpg"
output_path = "/home/duck/code/Open_Duck_Mini_Runtime/scripts/aze.jpg"

try:
    # Use the Pi's native command-line tool to take an immediate photo
    subprocess.run(["rpicam-still", "-o", temp_raw_path, "--immediate", "--width", "1024", "--height", "1024"], check=True)
    print("System image capture successful.")

    # Load the captured image into OpenCV
    im = cv2.imread(temp_raw_path)
    
    if im is None:
        raise FileNotFoundError("Failed to load captured image from disk.")

    # Resize the image to your 512x512 target
    im = cv2.resize(im, (512, 512))

    # CRITICAL FIX: Rotate 90 degrees clockwise to fix the -90 degree offset
    im = cv2.rotate(im, cv2.ROTATE_90_CLOCKWISE)

    # Save the final image
    cv2.imwrite(output_path, im)
    print(f"Success! Image processed, rotated, and saved to: {output_path}")

finally:
    # Clean up the temporary raw file if it exists
    if os.path.exists(temp_raw_path):
        os.remove(temp_raw_path)
