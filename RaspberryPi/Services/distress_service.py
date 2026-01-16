#!/usr/bin/env python3
"""
Distress Response Service

Listens for distress signals from ESP32 and responds with:
- Animation on TFT display
- Sound command to ESP32

Can be configured by mobile app to change animation/sound selection.
"""

import socket
import threading
import time
import os
import sys
from PIL import Image, ImageSequence
import digitalio
import board
import adafruit_rgb_display.ili9341 as ili9341

# ======================
# Configuration
# ======================

# ESP32 Communication
UDP_LISTEN_PORT = 4210      # Receive sensor data from ESP32
ESP32_IP = "192.168.4.1"
ESP32_CMD_PORT = 5006       # Send commands to ESP32

# Animation paths (5 animations)
ANIMATIONS = {
    1: "/home/abdul/fyp2/assets/animations/01_jellyfish.gif",
    2: "/home/abdul/fyp2/assets/animations/02_lava_lamp.gif",
    3: "/home/abdul/fyp2/assets/animations/03_aquarium.gif",
    4: "/home/abdul/fyp2/assets/animations/04_aurora.gif",
    5: "/home/abdul/fyp2/assets/animations/05_bubbles.gif",
}

# Sound tracks on ESP32 (13 sounds + 1 alarm)
SOUNDS = {
    1: "Anak Ayam",
    2: "Mr Bean Theme",
    3: "Anak Itik Tokwi",
    4: "Nenek sudah Tua",
    5: "Semangat Anak",
    6: "Dimana Dia",
    7: "Pintu Rindu",
    8: "Bangkitlah Anak",
    9: "Langit Biru",
    10: "Seribu Tahun",
    11: "Al-Ikhlas",
    12: "Al-Kautsar",
    13: "Al-Asr",
    14: "Find My Device (Alarm)",  # Reserved for Find My ESP32 feature
}

# Default settings (can be changed by mobile app)
current_animation = 1       # Default animation (1-5)
current_sound = 1           # Default sound (1-10)
animation_enabled = True    # Enable/disable animation response
sound_enabled = True        # Enable/disable sound response

# Child profile state (default OFF for power saving and privacy)
# When False: only core distress detection runs
# When True: camera, sensor, streaming services are enabled
child_profile_active = False

# Distress detection - Pi only responds to explicit DISTRESS alerts from ESP32
# ESP32 handles its own distress detection and sound playback
# Pi only plays animations when ESP32 signals distress

# Cooldown between responses (seconds)
RESPONSE_COOLDOWN = 5
last_response_time = 0

# ESP32 connection tracking
_esp32_connected = False
_esp32_beacon_detected = False
_esp32_last_data_time = 0
ESP32_CONNECTION_TIMEOUT = 10  # Seconds without data before considered disconnected

# Callbacks for external notification (used by main_service)
_on_esp32_data_callback = None
_on_distress_callback = None

_last_volume = None
_last_volume_time = 0

def set_on_esp32_data_callback(callback):
    """Set callback for when ESP32 sensor data is received.

    Callback signature: callback(parsed_data: dict)
    parsed_data contains: device, time, psi_max, grip_state, motion, alert, dominant_type, etc.
    """
    global _on_esp32_data_callback
    _on_esp32_data_callback = callback


def set_on_distress_callback(callback):
    """Set callback for when distress is detected.

    Callback signature: callback(alert_type: str, distress_type: str, reason: str, distress_motion: str)
    alert_type: "PATTERN_3GRIP" or "MOTION_3X"
    distress_type: "Stressed", "Tantrum", or "Unknown"
    reason: Human-readable description
    distress_motion: Motion type for MOTION_3X (e.g., "Impact", "ViolentShake") or "none"
    """
    global _on_distress_callback
    _on_distress_callback = callback


# ======================
# ESP32 Connection Status
# ======================

def update_esp32_connection():
    """Update ESP32 connection status (call when data is received from ESP32)."""
    global _esp32_connected, _esp32_last_data_time
    was_connected = _esp32_connected
    _esp32_connected = True
    _esp32_last_data_time = time.time()
    if not was_connected:
        print(f"[ESP32] 🟢 Connection status changed: CONNECTED (received data)")


def is_esp32_connected():
    """Check if ESP32 is currently connected (received data within timeout)."""
    global _esp32_connected
    if _esp32_last_data_time == 0:
        return False
    # Check if we received data within the timeout period
    if time.time() - _esp32_last_data_time > ESP32_CONNECTION_TIMEOUT:
        _esp32_connected = False
    return _esp32_connected


def set_esp32_beacon_detected(detected: bool):
    """Set ESP32 BLE beacon detection status."""
    global _esp32_beacon_detected
    _esp32_beacon_detected = detected


def is_esp32_beacon_detected():
    """Check if ESP32 BLE beacon is detected."""
    return _esp32_beacon_detected


def set_volume(volume: int):
    global _last_volume, _last_volume_time
    print(f"[DEBUG] set_volume called with: {volume}")
    volume = max(0, min(30, volume))
    now = time.time()
    # Ignore duplicate volume
    if volume == _last_volume:
        print(f"[DEBUG] Ignoring duplicate volume: {volume}")
        return
    # Rate-limit: max 5 per second
    if now - _last_volume_time < 0.2:
        print(f"[DEBUG] Rate-limited (last: {_last_volume_time:.2f}, now: {now:.2f})")
        return
    _last_volume = volume
    _last_volume_time = now
    send_esp32_command(f"VOLUME:{volume}")
    print(f"[UDP] Sent volume {volume}")

# Logo path for returning to idle
LOGO_PATH = "/home/abdul/fyp2/assets/image/logo.png"

# Animation duration (seconds)
ANIMATION_DURATION = 20

# Set to True to stretch animations to fill entire screen (may distort)
# Set to False to keep aspect ratio (black bars if needed)
FILL_SCREEN = True

# ======================
# Display Setup
# ======================

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

WIDTH = display.width    # 240
HEIGHT = display.height  # 320
IMG_WIDTH = HEIGHT       # 320 (swapped for rotation)
IMG_HEIGHT = WIDTH       # 240

# Animation control
animation_running = False
animation_thread = None
stop_animation = threading.Event()


# ======================
# Display Functions
# ======================

def display_frame(image, fill_screen=True):
    """Display a single frame on the TFT.

    Args:
        image: PIL Image to display
        fill_screen: If True, stretch to fill entire screen (may distort)
                    If False, maintain aspect ratio (may have black bars)
    """
    # Handle transparency
    if image.mode == "RGBA":
        background = Image.new("RGB", image.size, "black")
        background.paste(image, mask=image.split()[3])
        image = background
    elif image.mode == "P":
        # Handle palette mode (common in GIFs)
        image = image.convert("RGBA")
        background = Image.new("RGB", image.size, "black")
        if image.mode == "RGBA":
            background.paste(image, mask=image.split()[3])
        else:
            background.paste(image)
        image = background
    else:
        image = image.convert("RGB")

    if fill_screen:
        # Stretch to fill entire screen
        image = image.resize((IMG_WIDTH, IMG_HEIGHT), Image.LANCZOS)
    else:
        # Maintain aspect ratio with black bars
        image.thumbnail((IMG_WIDTH, IMG_HEIGHT), Image.LANCZOS)
        background = Image.new("RGB", (IMG_WIDTH, IMG_HEIGHT), "black")
        offset = ((IMG_WIDTH - image.width) // 2, (IMG_HEIGHT - image.height) // 2)
        background.paste(image, offset)
        image = background

    display.image(image)


def play_animation(animation_id, duration=ANIMATION_DURATION, fill_screen=True):
    """Play a GIF animation on the display.

    Args:
        animation_id: Animation ID (1-5)
        duration: How long to play the animation in seconds
        fill_screen: If True, stretch frames to fill entire screen
    """
    global animation_running

    gif_path = ANIMATIONS.get(animation_id)
    if not gif_path or not os.path.exists(gif_path):
        print(f"Animation {animation_id} not found: {gif_path}")
        return

    print(f"Playing animation {animation_id}: {gif_path} (fill_screen={fill_screen})")
    animation_running = True
    stop_animation.clear()

    try:
        gif = Image.open(gif_path)
        frames = []
        durations = []

        # Get the base canvas size from the GIF
        canvas_size = gif.size

        # Extract all frames properly (handle optimized GIFs)
        # Some GIFs have frames smaller than the canvas
        last_frame = None
        for frame in ImageSequence.Iterator(gif):
            # Create a full canvas for each frame
            new_frame = Image.new("RGBA", canvas_size, (0, 0, 0, 255))

            # Handle disposal method for proper animation
            if last_frame is not None and frame.info.get('disposal', 0) != 2:
                new_frame.paste(last_frame)

            # Paste the current frame at its position
            frame_rgba = frame.convert("RGBA")
            new_frame.paste(frame_rgba, frame.info.get('offset', (0, 0)), frame_rgba)

            frames.append(new_frame.copy())
            durations.append(frame.info.get('duration', 100) / 1000.0)
            last_frame = new_frame.copy()

        if not frames:
            print("No frames in GIF")
            return

        print(f"Loaded {len(frames)} frames, canvas size: {canvas_size}")

        start_time = time.time()
        frame_index = 0

        while not stop_animation.is_set():
            if time.time() - start_time >= duration:
                break

            display_frame(frames[frame_index], fill_screen=fill_screen)
            time.sleep(durations[frame_index])
            frame_index = (frame_index + 1) % len(frames)

    except Exception as e:
        print(f"Animation error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        animation_running = False
        # Return to logo after animation
        display_logo()


def display_logo():
    """Display the project logo."""
    if os.path.exists(LOGO_PATH):
        image = Image.open(LOGO_PATH)
        display_frame(image, fill_screen=FILL_SCREEN)
        print("Returned to logo")
    else:
        # Clear to black
        image = Image.new("RGB", (IMG_WIDTH, IMG_HEIGHT), "black")
        display.image(image)


def stop_current_animation():
    """Stop any running animation."""
    global animation_thread
    stop_animation.set()
    if animation_thread and animation_thread.is_alive():
        animation_thread.join(timeout=1)


# ======================
# ESP32 Communication
# ======================

def send_esp32_command(command):
    """Send a command to ESP32."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(command.encode(), (ESP32_IP, ESP32_CMD_PORT))
        sock.close()
        print(f"Sent to ESP32: {command}")
    except Exception as e:
        print(f"Error sending to ESP32: {e}")


def play_sound(sound_id):
    """Tell ESP32 to play a sound (1-14)."""
    if 1 <= sound_id <= 14:
        # Debug: Print stack trace to see where this is called from
        import traceback
        print(f"\n[DEBUG] play_sound({sound_id}) called from:")
        print("".join(traceback.format_stack()[-4:-1]))  # Show last 3 stack frames
        send_esp32_command(f"PLAY:{sound_id}")


def stop_sound():
    """Tell ESP32 to stop sound."""
    send_esp32_command("PLAY:STOP")


# ======================
# Distress Detection
# ======================

def parse_esp32_message(message):
    """Parse ESP32 sensor data message."""
    data = {}
    try:
        fields = message.split(',')
        for field in fields:
            if ':' in field:
                key, value = field.split(':', 1)
                data[key] = value
    except Exception as e:
        print(f"Parse error: {e}")
    return data

# Valid motion types (for reference)
VALID_MOTIONS = ["Impact", "ViolentShake", "FreeFall", "Bounce", "Spinning", "Rocking", "Tremble", "None"]

def is_distress_signal(data):
      """Check if the data indicates a distress signal.

      Pi ONLY responds to these specific alerts from ESP32:
      1. alert:PATTERN_3GRIP - 3 grips beyond stress threshold within 3s gaps
      2. alert:MOTION_3X - 3 consecutive same motions detected

      Single motions or grips do NOT trigger animation!

      Returns:
          tuple: (is_distress: bool, alert_type: str, distress_type: str, reason: str, distress_motion: str)
      """
      alert = data.get("alert", "")

      # Check for 3-grip pattern alert
      if "PATTERN_3GRIP" in alert:
          dominant_type = data.get("dominant_type", "Unknown")
          return True, "PATTERN_3GRIP", dominant_type, f"3-Grip Pattern (Dominant: {dominant_type})", "none"

      # Check for 3 consecutive motions alert
      if "MOTION_3X" in alert:
          motion_type = data.get("motion_type", data.get("motion", "Unknown"))
          # For motion alerts, use the grip_state as distress type if available
          distress_type = data.get("dominant_type", data.get("grip_state", "Unknown"))
          return True, "MOTION_3X", distress_type, f"3x Consecutive Motion ({motion_type})", motion_type

      return False, "none", "none", None, "none"


def handle_distress(reason):
    """Respond to a distress signal.

    Pi plays both animation and sound on distress.
    Sound uses the current_sound configured by mobile app.
    Animation uses the current_animation configured by mobile app.
    """
    global last_response_time, animation_thread

    current_time = time.time()

    # Check cooldown
    if current_time - last_response_time < RESPONSE_COOLDOWN:
        return

    last_response_time = current_time
    print(f"\n*** DISTRESS DETECTED: {reason} ***")
    print(f"[DEBUG] Child paired: {child_profile_active}, Current sound: {current_sound}, Current animation: {current_animation}")

    # Stop any current animation
    stop_current_animation()

    # Play sound on ESP32 using the configured sound
    if sound_enabled:
        print(f"[DEBUG] Calling play_sound({current_sound}) due to distress: {reason}")
        play_sound(current_sound)
        print(f"Playing sound {current_sound}: {SOUNDS.get(current_sound, 'Unknown')} on ESP32")

    # Play animation on display
    if animation_enabled:
        animation_thread = threading.Thread(
            target=play_animation,
            args=(current_animation, ANIMATION_DURATION, FILL_SCREEN)
        )
        animation_thread.start()
        print(f"Playing animation {current_animation}")


# ======================
# Settings Control (for Mobile App)
# ======================

def set_animation(animation_id):
    """Set the animation to play on distress (1-5)."""
    global current_animation
    if 1 <= animation_id <= 5:
        current_animation = animation_id
        print(f"Animation set to {animation_id}")
        return True
    return False


def set_sound(sound_id):
    """Set the sound to play on distress (1-13). Sound 14 is reserved for alarm."""
    global current_sound
    if 1 <= sound_id <= 13:
        current_sound = sound_id
        print(f"Sound set to {sound_id}: {SOUNDS.get(sound_id, 'Unknown')}")
        return True
    return False


def find_my_device():
    """Play alarm sound (14) on ESP32 to locate the device."""
    print("*** FIND MY DEVICE - Playing alarm on ESP32 ***")
    play_sound(14)
    return True


def enable_animation(enabled):
    """Enable or disable animation response."""
    global animation_enabled
    animation_enabled = enabled
    print(f"Animation {'enabled' if enabled else 'disabled'}")


def enable_sound(enabled):
    """Enable or disable sound response."""
    global sound_enabled
    sound_enabled = enabled
    print(f"Sound {'enabled' if enabled else 'disabled'}")


def set_child_profile_active(active: bool):
    """Enable or disable child profile (controls optional services).

    When active: camera, sensor, streaming services run
    When inactive: only core distress detection runs (saves power, ensures privacy)
    """
    global child_profile_active
    child_profile_active = active
    print(f"[Profile] Child profile {'activated' if active else 'deactivated'}")


def is_child_profile_active() -> bool:
    """Check if child profile is currently active."""
    return child_profile_active


def get_settings():
    """Get current settings as dict (compact version for BLE notifications).

    Returns only essential settings to keep BLE payload small (~200 bytes).
    Full animation/sound lists are available via get_full_settings().
    """
    esp32_status = is_esp32_connected()
    beacon_status = is_esp32_beacon_detected()
    return {
        "current_animation": current_animation,
        "current_sound": current_sound,
        "animation_enabled": animation_enabled,
        "sound_enabled": sound_enabled,
        "child_profile_active": child_profile_active,
        "esp32_connected": esp32_status,
        "esp32_beacon_detected": beacon_status,
    }


def get_full_settings():
    """Get full settings including animation/sound lists.

    Use this for direct characteristic reads, not for notifications.
    """
    base = get_settings()
    base.update({
        "available_animations": list(ANIMATIONS.keys()),
        "available_sounds": {k: v for k, v in SOUNDS.items() if k <= 13},
    })
    return base


def play_animation_now(animation_id):
    """Immediately play the specified animation on the TFT display.

    This is called by mobile app to preview/play an animation.
    Distress signals will still take priority (handle_distress calls
    stop_current_animation before starting its own animation).

    Args:
        animation_id: Animation ID (1-5)

    Returns:
        bool: True if animation started, False if invalid ID
    """
    global animation_thread

    if animation_id < 1 or animation_id > 5:
        print(f"[Distress] Invalid animation ID: {animation_id} (must be 1-5)")
        return False

    print(f"[Distress] Mobile app requested play animation {animation_id}")

    # Stop any current animation first
    stop_current_animation()

    # Start the requested animation in a new thread
    animation_thread = threading.Thread(
        target=play_animation,
        args=(animation_id, ANIMATION_DURATION, FILL_SCREEN)
    )
    animation_thread.start()

    return True


# ======================
# Main Service
# ======================

def start_listener():
    """Start listening for ESP32 data."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", UDP_LISTEN_PORT))
    sock.settimeout(1.0)

    print(f"Listening for ESP32 on UDP port {UDP_LISTEN_PORT}")
    print(f"Default animation: {current_animation}")
    print("Waiting for 'alert' from ESP32...")
    print("-" * 50)

    # Show logo initially
    display_logo()

    try:
        while True:
            try:
                data, addr = sock.recvfrom(1024)
                message = data.decode('utf-8')
                print(f"[UDP] Received from {addr}: {message[:80]}")  # Debug log

                # Parse and check for distress
                parsed = parse_esp32_message(message)

                # Update ESP32 connection status (we received data, so it's connected)
                update_esp32_connection()

                # Call ESP32 data callback (for BLE sensor updates)
                if _on_esp32_data_callback:
                    try:
                        _on_esp32_data_callback(parsed)
                    except Exception as cb_err:
                        print(f"ESP32 data callback error: {cb_err}")

                # Check for distress signal
                is_distress, alert_type, distress_type, reason, distress_motion = is_distress_signal(parsed)

                if is_distress:
                    print(f"[DEBUG] Distress signal detected from ESP32 data!")
                    print(f"[DEBUG] Alert type: {alert_type}, Reason: {reason}")
                    print(f"[DEBUG] ESP32 data: {parsed}")

                    # Call distress callback (for BLE distress alert notification)
                    if _on_distress_callback:
                        try:
                            _on_distress_callback(alert_type, distress_type, reason, distress_motion)
                        except Exception as cb_err:
                            print(f"Distress callback error: {cb_err}")

                    handle_distress(reason)

            except socket.timeout:
                continue
            except Exception as e:
                print(f"Error: {e}")

    except KeyboardInterrupt:
        print("\nStopping distress service...")
    finally:
        stop_current_animation()
        sock.close()
        display_logo()


if __name__ == "__main__":
    print("=" * 50)
    print("Distress Response Service")
    print("=" * 50)
    print(f"Animations available: {list(ANIMATIONS.keys())}")
    print(f"Sounds available (for mobile app): {list(SOUNDS.keys())}")
    print("-" * 50)
    print("Pi responds to 'alert:DISTRESS' from ESP32 with animations ONLY")
    print("ESP32 handles its own sound playback")
    print("Pi sends sound commands only on mobile app request")
    print("=" * 50)

    start_listener()
