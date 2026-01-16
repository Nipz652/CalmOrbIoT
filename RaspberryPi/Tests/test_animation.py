#!/usr/bin/env python3
"""
Animation Tester for ILI9341 Display
Tests GIF animations from the assets/animations folder

Usage:
    python test_animation.py                    # List all animations
    python test_animation.py 1                  # Play animation #1
    python test_animation.py jellyfish          # Play animation containing 'jellyfish'
    python test_animation.py --all              # Play all animations sequentially
"""

import os
import sys
import time
import glob

# Configuration
ANIMATIONS_DIR = "/home/abdul/fyp2/assets/animations"

# Try to import display libraries
try:
    import digitalio
    import board
    from PIL import Image
    from adafruit_rgb_display import ili9341
    DISPLAY_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Display libraries not available: {e}")
    DISPLAY_AVAILABLE = False

# Initialize display if available
display = None
SCREEN_WIDTH = 320
SCREEN_HEIGHT = 240

if DISPLAY_AVAILABLE:
    try:
        CS_PIN = digitalio.DigitalInOut(board.CE0)      # GPIO 8
        DC_PIN = digitalio.DigitalInOut(board.D24)      # GPIO 24 (DC)
        RESET_PIN = digitalio.DigitalInOut(board.D25)   # GPIO 25 (RESET)

        spi = board.SPI()
        display = ili9341.ILI9341(
            spi,
            rotation=180,
            cs=CS_PIN,
            dc=DC_PIN,
            rst=RESET_PIN,
            baudrate=32000000
        )
        SCREEN_WIDTH = display.width
        SCREEN_HEIGHT = display.height
        print(f"Display initialized: {SCREEN_WIDTH}x{SCREEN_HEIGHT}")
    except Exception as e:
        print(f"Warning: Could not initialize display: {e}")
        display = None


def get_animations():
    """Get list of all GIF files in animations folder"""
    pattern = os.path.join(ANIMATIONS_DIR, "*.gif")
    files = sorted(glob.glob(pattern))
    return files


def list_animations():
    """Display list of available animations"""
    animations = get_animations()

    if not animations:
        print("No GIF files found in:")
        print(f"  {ANIMATIONS_DIR}")
        print("\nAdd .gif files to test them.")
        return []

    print("=" * 50)
    print("Available Animations")
    print("=" * 50)

    for i, path in enumerate(animations, 1):
        filename = os.path.basename(path)
        size = os.path.getsize(path) / 1024 / 1024  # MB
        print(f"  {i}. {filename} ({size:.2f} MB)")

    print("=" * 50)
    print(f"Total: {len(animations)} animation(s)")
    print()
    print("Usage:")
    print("  python test_animation.py <number>   # Play by number")
    print("  python test_animation.py <name>     # Play by name")
    print("  python test_animation.py --all      # Play all")
    print("  python test_animation.py --info     # Show info only")
    print()

    return animations


def play_animation(gif_path, duration=None):
    """Play GIF animation on ILI9341 display"""
    if not display:
        print("Error: Display not available")
        return False

    filename = os.path.basename(gif_path)
    print(f"\nPlaying: {filename}")
    print("Press Ctrl+C to stop")
    print("-" * 40)

    # Load GIF
    try:
        gif = Image.open(gif_path)
    except Exception as e:
        print(f"Error loading GIF: {e}")
        return False

    # Count frames
    frame_count = 0
    try:
        while True:
            frame_count += 1
            gif.seek(gif.tell() + 1)
    except EOFError:
        pass

    print(f"Frames: {frame_count}")
    print(f"Display: {SCREEN_WIDTH}x{SCREEN_HEIGHT}")

    gif.seek(0)
    start_time = time.time()

    # Rotation: 0, 90, 180, 270 - adjust if animation is oriented wrong
    FRAME_ROTATION = 270

    try:
        while True:
            for i in range(frame_count):
                gif.seek(i)
                frame = gif.copy().convert("RGB")

                # Resize to match display exactly (width=240, height=320)
                frame = frame.resize((display.width, display.height), Image.Resampling.LANCZOS)

                # Rotate frame if needed
                if FRAME_ROTATION != 0:
                    frame = frame.rotate(FRAME_ROTATION, expand=False)

                display.image(frame)

                delay = gif.info.get('duration', 100) / 1000.0
                time.sleep(delay)

                # Check duration limit
                if duration and (time.time() - start_time) >= duration:
                    print(f"\nDuration limit ({duration}s) reached")
                    return True

    except KeyboardInterrupt:
        print("\nStopped by user")

    return True


def show_animation_info(gif_path):
    """Display GIF info in terminal (no display required)"""
    filename = os.path.basename(gif_path)
    print(f"\nAnalyzing: {filename}")
    print("-" * 40)

    try:
        gif = Image.open(gif_path)

        # Count frames
        frame_count = 0
        total_duration = 0
        try:
            while True:
                frame_count += 1
                total_duration += gif.info.get('duration', 100)
                gif.seek(gif.tell() + 1)
        except EOFError:
            pass

        gif.seek(0)

        print(f"  Resolution: {gif.size[0]}x{gif.size[1]}")
        print(f"  Frames: {frame_count}")
        print(f"  Duration: {total_duration/1000:.1f} seconds")
        print(f"  FPS: {frame_count / (total_duration/1000):.1f}")
        print(f"  File size: {os.path.getsize(gif_path)/1024/1024:.2f} MB")

        return True

    except Exception as e:
        print(f"Error: {e}")
        return False


def find_animation(search_term, animations):
    """Find animation by number or name"""
    # Try as number
    try:
        index = int(search_term) - 1
        if 0 <= index < len(animations):
            return animations[index]
    except ValueError:
        pass

    # Try as name (partial match)
    search_lower = search_term.lower()
    for path in animations:
        if search_lower in os.path.basename(path).lower():
            return path

    return None


def main():
    args = sys.argv[1:]
    animations = get_animations()

    # No arguments - list animations
    if not args:
        list_animations()
        return

    # --all flag - play all animations
    if args[0] == "--all":
        if not animations:
            print("No animations found!")
            return

        print(f"Playing all {len(animations)} animations (10 seconds each)")
        print("Press Ctrl+C to stop")

        for path in animations:
            try:
                play_animation(path, duration=10)
            except KeyboardInterrupt:
                print("\nStopped by user")
                break
        return

    # --info flag - show info only
    if args[0] == "--info":
        if len(args) > 1:
            path = find_animation(args[1], animations)
            if path:
                show_animation_info(path)
            else:
                print(f"Animation not found: {args[1]}")
        else:
            for path in animations:
                show_animation_info(path)
        return

    # Find and play specific animation
    path = find_animation(args[0], animations)

    if not path:
        print(f"Animation not found: {args[0]}")
        print()
        list_animations()
        return

    # Play animation
    play_animation(path)


if __name__ == "__main__":
    main()
