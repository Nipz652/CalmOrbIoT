import cv2
import digitalio
import board
from PIL import Image
import adafruit_rgb_display.ili9341 as ili9341

# -------------------------------
# Initialize TFT Display via SPI
# -------------------------------

spi = board.SPI()

cs_pin = digitalio.DigitalInOut(board.CE0)      # GPIO 8 → TFT CS
dc_pin = digitalio.DigitalInOut(board.D24)      # GPIO 24 → TFT DC
reset_pin = digitalio.DigitalInOut(board.D25)   # GPIO 25 → TFT RESET

display = ili9341.ILI9341(
    spi,
    rotation=90,   # You may change to 0/90/180/270 depending on your orientation
    cs=cs_pin,
    dc=dc_pin,
    rst=reset_pin,
    baudrate=32000000
)

WIDTH = display.width
HEIGHT = display.height

print("TFT Resolution:", WIDTH, "x", HEIGHT)

# --------------------------------
# Initialize Webcam
# --------------------------------

cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("❌ ERROR: Cannot open webcam (/dev/video0)")
    exit()

print("✅ Webcam Opened Successfully")

# --------------------------------
# Main Loop
# --------------------------------

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("❌ Failed to grab frame")
            break

        # Convert BGR → RGB
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Convert to PIL Image
        pil_img = Image.fromarray(frame_rgb)

        # Resize EXACTLY to the TFT resolution
        pil_img = pil_img.resize((HEIGHT, WIDTH), Image.BILINEAR)

        # Ensure correct RGB format
        pil_img = pil_img.convert("RGB")

        # Display to TFT
        display.image(pil_img)

        # Exit using CTRL+C
except KeyboardInterrupt:
    print("\nStopping...")

cap.release()
print("Camera released.")

