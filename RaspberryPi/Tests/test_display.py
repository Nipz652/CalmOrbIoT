#!/usr/bin/env python3
"""
ILI9341 Display Test for Raspberry Pi
Tests the 320x240 SPI TFT display

Wiring (from config/settings.py):
    MOSI  -> GPIO 10 (Pin 19)
    SCLK  -> GPIO 11 (Pin 23)
    CS    -> GPIO 8  (Pin 24)
    DC    -> GPIO 25 (Pin 22)
    RESET -> GPIO 24 (Pin 18)
    VCC   -> 3.3V
    GND   -> GND
"""

import time
import sys
import os
import board

# Add project root to path
sys.path.insert(0, '/home/abdul/fyp2')

try:
    import digitalio
    import board
    from PIL import Image, ImageDraw, ImageFont
    from adafruit_rgb_display import ili9341
except ImportError as e:
    print(f"Missing library: {e}")
    print("\nInstall with:")
    print("  pip3 install adafruit-circuitpython-rgb-display Pillow --break-system-packages")
    sys.exit(1)

# Display configuration (matching test_cam.py which works)
CS_PIN = digitalio.DigitalInOut(board.CE0)      # GPIO 8
DC_PIN = digitalio.DigitalInOut(board.D24)      # GPIO 24 (DC)
RESET_PIN = digitalio.DigitalInOut(board.D25)   # GPIO 25 (RESET)

spi = board.SPI()
display = ili9341.ILI9341(
    spi,
    rotation=180,   # You may change to 0/90/180/270 depending on your orientation
    cs=CS_PIN,
    dc=DC_PIN,
    rst=RESET_PIN,
    baudrate=32000000
)

SCREEN_WIDTH = display.width
SCREEN_HEIGHT = display.height
ROTATION = 90  # Matching test_cam.py

# SPI Speed
BAUDRATE = 32000000  # 32MHz


def init_display():
    """Initialize the ILI9341 display"""
    print("Initializing ILI9341 display...")
    print(f"  CS: GPIO 8 (CE0)")
    print(f"  DC: GPIO 25")
    print(f"  RST: GPIO 24")
    print(f"  SPI Speed: {BAUDRATE // 1000000}MHz")

    spi = board.SPI()

    display = ili9341.ILI9341(
        spi,
        cs=CS_PIN,
        dc=DC_PIN,
        rst=RESET_PIN,
        baudrate=BAUDRATE,
        rotation=ROTATION,
        width=SCREEN_WIDTH,
        height=SCREEN_HEIGHT,
    )

    print(f"  Display size: {display.width}x{display.height}")
    return display


def test_colors(display):
    """Test basic colors"""
    print("\nTest 1: Color Test")
    print(f"  Display dimensions: {display.width}x{display.height}")

    colors = [
        ("Red", (255, 0, 0)),
        ("Green", (0, 255, 0)),
        ("Blue", (0, 0, 255)),
        ("White", (255, 255, 255)),
        ("Black", (0, 0, 0)),
    ]

    # Use actual display dimensions (swapped due to rotation=90)
    width = display.height
    height = display.width

    for name, color in colors:
        print(f"  Showing {name}...")
        image = Image.new("RGB", (width, height), color)
        display.image(image)
        time.sleep(1)


def test_text(display):
    """Test text rendering"""
    print("\nTest 2: Text Test")

    # Swapped due to rotation=90
    width = display.height
    height = display.width

    image = Image.new("RGB", (width, height), (0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Try to use a font, fallback to default
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
        small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
    except:
        font = ImageFont.load_default()
        small_font = font

    draw.text((10, 10), "ILI9341 Test", font=font, fill=(255, 255, 255))
    draw.text((10, 50), "320 x 240 pixels", font=small_font, fill=(0, 255, 0))
    draw.text((10, 80), "Pi Hub Display", font=small_font, fill=(255, 255, 0))
    draw.text((10, 110), "Working!", font=font, fill=(0, 255, 255))

    display.image(image)
    time.sleep(3)


def test_animation(display):
    """Test simple animation"""
    print("\nTest 3: Animation Test (bouncing ball)")

    # Swapped due to rotation=90
    width = display.height
    height = display.width

    ball_x, ball_y = width // 2, height // 2
    ball_dx, ball_dy = 5, 3
    ball_radius = 20

    for _ in range(100):
        # Create frame
        image = Image.new("RGB", (width, height), (0, 0, 50))
        draw = ImageDraw.Draw(image)

        # Draw ball
        draw.ellipse(
            [ball_x - ball_radius, ball_y - ball_radius,
             ball_x + ball_radius, ball_y + ball_radius],
            fill=(255, 100, 100)
        )

        # Update position
        ball_x += ball_dx
        ball_y += ball_dy

        # Bounce off walls
        if ball_x <= ball_radius or ball_x >= width - ball_radius:
            ball_dx = -ball_dx
        if ball_y <= ball_radius or ball_y >= height - ball_radius:
            ball_dy = -ball_dy

        display.image(image)

    print("  Animation complete")


def test_gif(display, gif_path):
    """Test GIF playback"""
    print(f"\nTest 4: GIF Playback")
    print(f"  File: {gif_path}")

    if not os.path.exists(gif_path):
        print(f"  Error: File not found")
        return

    try:
        gif = Image.open(gif_path)
    except Exception as e:
        print(f"  Error loading GIF: {e}")
        return

    # Count frames
    frame_count = 0
    try:
        while True:
            frame_count += 1
            gif.seek(gif.tell() + 1)
    except EOFError:
        pass

    print(f"  Frames: {frame_count}")
    print(f"  Playing animation (press Ctrl+C to stop)...")

    gif.seek(0)

    try:
        while True:
            for i in range(frame_count):
                gif.seek(i)
                frame = gif.copy().convert("RGB")
                # Resize to fit display
                frame = frame.resize((display.width, display.height), Image.Resampling.LANCZOS)
                # Rotate 270 degrees to match display orientation
                frame = frame.rotate(270, expand=False)
                display.image(frame)

                delay = gif.info.get('duration', 100) / 1000.0
                time.sleep(delay)

    except KeyboardInterrupt:
        print("\n  Stopped by user")


def main():
    print("=" * 50)
    print("ILI9341 Display Test")
    print("=" * 50)

    # Initialize display
    try:
        display = init_display()
    except Exception as e:
        print(f"\nError initializing display: {e}")
        print("\nCheck your wiring:")
        print("  MOSI  -> GPIO 10 (Pin 19)")
        print("  SCLK  -> GPIO 11 (Pin 23)")
        print("  CS    -> GPIO 8  (Pin 24)")
        print("  DC    -> GPIO 25 (Pin 22)")
        print("  RESET -> GPIO 24 (Pin 18)")
        print("  VCC   -> 3.3V")
        print("  GND   -> GND")
        sys.exit(1)

    # Run tests
    if len(sys.argv) > 1:
        # Test specific GIF
        gif_path = sys.argv[1]
        if not gif_path.startswith('/'):
            gif_path = f"/home/abdul/fyp2/assets/animations/{gif_path}"
        if not gif_path.endswith('.gif'):
            gif_path += '.gif'
        test_gif(display, gif_path)
    else:
        # Run all tests
        test_colors(display)
        test_text(display)
        test_animation(display)

        # Test first GIF if available
        animations_dir = "/home/abdul/fyp2/assets/animations"
        gifs = sorted([f for f in os.listdir(animations_dir) if f.endswith('.gif')])
        if gifs:
            test_gif(display, os.path.join(animations_dir, gifs[0]))

    print("\n" + "=" * 50)
    print("Test Complete!")
    print("=" * 50)


if __name__ == "__main__":
    main()
