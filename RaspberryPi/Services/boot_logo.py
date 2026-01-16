#!/usr/bin/env python3
"""
Boot Logo Display for ILI9341
Displays a PNG logo on startup and keeps it displayed
"""

import sys
import time

try:
    import digitalio
    import board
    from PIL import Image
    from adafruit_rgb_display import ili9341
except ImportError as e:
    print(f"Error: Missing library - {e}")
    sys.exit(1)

# Logo path - change this to your logo file
LOGO_PATH = "/home/abdul/fyp2/assets/logo.png"

# Display configuration
CS_PIN = digitalio.DigitalInOut(board.CE0)      # GPIO 8
DC_PIN = digitalio.DigitalInOut(board.D24)      # GPIO 24
RESET_PIN = digitalio.DigitalInOut(board.D25)   # GPIO 25

# Frame rotation (270 = correct landscape orientation)
FRAME_ROTATION = 270


def init_display():
    """Initialize ILI9341 display"""
    spi = board.SPI()
    display = ili9341.ILI9341(
        spi,
        rotation=180,
        cs=CS_PIN,
        dc=DC_PIN,
        rst=RESET_PIN,
        baudrate=32000000
    )
    return display


def display_logo(display, logo_path):
    """Display logo on screen"""
    try:
        # Load logo
        logo = Image.open(logo_path).convert("RGB")

        # Resize to fit display
        logo = logo.resize((display.width, display.height), Image.Resampling.LANCZOS)

        # Rotate to correct orientation
        if FRAME_ROTATION != 0:
            logo = logo.rotate(FRAME_ROTATION, expand=False)

        # Display logo
        display.image(logo)
        print(f"Logo displayed: {logo_path}")
        return True

    except FileNotFoundError:
        print(f"Error: Logo not found at {logo_path}")
        print("Please add your logo.png to /home/abdul/fyp2/assets/")

        # Display a default colored screen instead
        default = Image.new("RGB", (display.width, display.height), (0, 50, 100))
        display.image(default)
        return False

    except Exception as e:
        print(f"Error displaying logo: {e}")
        return False


def main():
    print("Initializing boot logo...")

    display = init_display()
    print(f"Display: {display.width}x{display.height}")

    # Check for custom logo path argument
    logo_path = LOGO_PATH
    if len(sys.argv) > 1:
        logo_path = sys.argv[1]

    display_logo(display, logo_path)
    print("Boot logo ready")


if __name__ == "__main__":
    main()
