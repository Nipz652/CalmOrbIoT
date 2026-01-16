#!/usr/bin/env python3
"""
Pattern Test - Roboflow Camera Setup Test with TFT Display

Based on working test_cam.py with Roboflow detection added.
Uses threading for smooth display while inference runs in background.
"""

import cv2
import time
import base64
import requests
import digitalio
import board
from PIL import Image, ImageDraw, ImageFont
import adafruit_rgb_display.ili9341 as ili9341
import threading

# Import settings from config
import sys
sys.path.insert(0, '/home/abdul/fyp2')
from config.settings import (
    ROBOFLOW_API_KEY,
    ROBOFLOW_MODEL_ID,
    ROBOFLOW_CONFIDENCE_THRESHOLD,
    BEHAVIOR_DETECTION_INTERVAL,
)

# --- TFT Setup (same as test_cam.py) ---
spi = board.SPI()

cs_pin = digitalio.DigitalInOut(board.CE0)
dc_pin = digitalio.DigitalInOut(board.D24)
reset_pin = digitalio.DigitalInOut(board.D25)

display = ili9341.ILI9341(
    spi,
    rotation=90,
    cs=cs_pin,
    dc=dc_pin,
    rst=reset_pin,
    baudrate=32000000
)

WIDTH = display.width
HEIGHT = display.height

print(f"TFT Resolution: {WIDTH}x{HEIGHT}")

# --- Webcam Setup ---
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("ERROR: Cannot open webcam")
    exit(1)

print("Webcam opened successfully")

# --- Font ---
try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
except:
    font = ImageFont.load_default()

# --- Shared state for threading ---
latest_label = None
latest_confidence = 0
inference_lock = threading.Lock()
inference_frame = None
inference_running = True

# --- Roboflow Inference (runs in background thread) ---
def run_inference(frame_bgr):
    """Send frame to Roboflow API."""
    _, buffer = cv2.imencode(".jpg", frame_bgr)
    img_base64 = base64.b64encode(buffer).decode("utf-8")

    url = f"https://detect.roboflow.com/{ROBOFLOW_MODEL_ID}"
    params = {
        "api_key": ROBOFLOW_API_KEY,
        "confidence": ROBOFLOW_CONFIDENCE_THRESHOLD,
    }

    response = requests.post(
        url,
        params=params,
        data=img_base64,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10,
    )
    return response.json()

def inference_thread():
    """Background thread for Roboflow inference."""
    global latest_label, latest_confidence, inference_frame, inference_running

    while inference_running:
        # Get frame to process
        with inference_lock:
            frame_to_process = inference_frame.copy() if inference_frame is not None else None

        if frame_to_process is not None:
            try:
                result = run_inference(frame_to_process)
                predictions = result.get("predictions", [])
                if predictions:
                    best = max(predictions, key=lambda p: p["confidence"])
                    with inference_lock:
                        latest_label = best["class"]
                        latest_confidence = best["confidence"]
                    print(f"[Detection] {latest_label} ({latest_confidence:.2f})")
                else:
                    with inference_lock:
                        latest_label = None
            except Exception as e:
                print(f"[Error] {e}")

        # Wait before next inference
        time.sleep(BEHAVIOR_DETECTION_INTERVAL)

# --- Distress behaviors ---
DISTRESS_BEHAVIORS = [
    "Aggressive_Behavior", "Head_Banging", "SIB_Bitting",
    "Covering_Ears", "Finger_Bitting",
]

# --- Start inference thread ---
inference_worker = threading.Thread(target=inference_thread, daemon=True)
inference_worker.start()

# --- Main Loop ---
print("\n" + "=" * 40)
print("Roboflow Camera Test (Smooth Display)")
print(f"Model: {ROBOFLOW_MODEL_ID}")
print(f"Inference interval: {BEHAVIOR_DETECTION_INTERVAL}s")
print("Press Ctrl+C to stop")
print("=" * 40 + "\n")

frame_count = 0

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Failed to grab frame")
            break

        frame_count += 1

        # Update frame for inference thread (non-blocking)
        with inference_lock:
            inference_frame = frame.copy()

        # Convert BGR -> RGB
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Convert to PIL Image
        pil_img = Image.fromarray(frame_rgb)

        # Resize EXACTLY to TFT resolution (HEIGHT, WIDTH - swapped!)
        pil_img = pil_img.resize((HEIGHT, WIDTH), Image.BILINEAR)

        # Ensure correct RGB format
        pil_img = pil_img.convert("RGB")

        # Draw label overlay if detection exists (read from shared state)
        with inference_lock:
            label = latest_label
            confidence = latest_confidence

        if label:
            draw = ImageDraw.Draw(pil_img)
            is_distress = label in DISTRESS_BEHAVIORS
            bg_color = (200, 50, 50) if is_distress else (50, 150, 50)

            text = f"{label} ({confidence:.0%})"
            draw.rectangle([(0, 0), (HEIGHT, 20)], fill=bg_color)
            draw.text((5, 3), text, font=font, fill=(255, 255, 255))

        # Display to TFT
        display.image(pil_img)

except KeyboardInterrupt:
    print("\nStopping...")
finally:
    inference_running = False
    cap.release()
    print(f"Total frames: {frame_count}")
