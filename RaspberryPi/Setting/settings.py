"""
Configuration settings for the Pi Hub

GPIO Reference (Raspberry Pi 4):
- DHT22: GPIO 4 (Pin 7)
- Display SPI: GPIO 10 (MOSI), 11 (SCLK), 8 (CE0), 24 (DC), 25 (RST)
- I2S Mic: GPIO 18 (SCK), 19 (WS), 20 (SD)
- Camera: CSI port (no GPIO)
- BLE: Built-in (no GPIO)
- ESP32: WiFi UDP (no GPIO)
"""

# ======================
# GPIO Pin Configuration
# ======================
# DHT22 Temperature Sensor
DHT22_PIN = 4  # GPIO 4 (Pin 7)

# Display (SPI)
DISPLAY_SPI_MOSI = 10   # GPIO 10 (Pin 19)
DISPLAY_SPI_SCLK = 11   # GPIO 11 (Pin 23)
DISPLAY_SPI_CS = 8      # GPIO 8 (Pin 24) - CE0
DISPLAY_DC = 25         # GPIO 25 (Pin 22)
DISPLAY_RESET = 24      # GPIO 24 (Pin 18)

# I2S Microphone (if using I2S instead of USB)
I2S_SCK = 18   # GPIO 18 (Pin 12)
I2S_WS = 19    # GPIO 19 (Pin 35)
I2S_SD = 20    # GPIO 20 (Pin 38)

# ======================
# BLE Configuration (Mobile App GATT Server)
# ======================
# Uses built-in Bluetooth on Pi 4
BLE_DEVICE_NAME = "PiHub"
BLE_SERVICE_UUID = "12345678-1234-5678-1234-56789abcdef0"
BLE_CHARACTERISTIC_UUID = "12345678-1234-5678-1234-56789abcdef1"

# ======================
# BLE Beacon Configuration (ESP32 Proximity Scanner)
# ======================
# ESP32 BLE beacon settings for proximity detection
ESP32_BEACON_NAME = "ESP32-StressBall"

# RSSI calibration - measured RSSI at 1 meter distance
# Calibrate for your environment (typical: -55 to -70 dBm)
ESP32_TX_POWER_AT_1M = -59

# Proximity zone thresholds (in dBm, more negative = weaker signal)
# Updated for container environment - increased range
BEACON_RSSI_NEAR = -99      # Stronger than -99 = NEAR (< 15m)
BEACON_RSSI_MEDIUM = -105   # -99 to -105 = MEDIUM (15-25m)
BEACON_RSSI_FAR = -110      # -105 to -110 = FAR (25-35m)
                            # Weaker than -110 = OUT_OF_RANGE (> 35m)

# Scanning parameters (optimized for catching intermittent ESP32 beacon)
BEACON_SCAN_INTERVAL = 0.1  # Seconds between scans (fast cycles to catch infrequent beacons)
BEACON_SCAN_DURATION = 3.0  # Duration of each scan (longer window to catch advertisements)
BEACON_RSSI_SAMPLES = 8     # Number of samples to average for smoothing (better noise reduction)
BEACON_LOST_TIMEOUT = 25.0  # Seconds before marking device as OUT_OF_RANGE (tolerant of gaps)
BEACON_ZONE_DEBOUNCE = 3    # Consecutive readings needed to change zone (prevents flickering)

# ======================
# WiFi/ESP32 Configuration
# ======================
# Communication via WiFi UDP (no GPIO required)
ESP32_IP = "192.168.4.1"  # ESP32 AP IP address
ESP32_PORT = 80
WIFI_SSID = "ESP32_StressBall"
WIFI_PASSWORD = "12345678"

# ======================
# Camera Configuration
# ======================
# Supports USB webcam (OpenCV) or Pi Camera Module (Picamera2)
CAMERA_TYPE = "usb"  # Options: "usb" (USB webcam) or "picamera" (Pi Camera Module)
CAMERA_DEVICE_INDEX = 0  # USB webcam device index (/dev/video0 = 0, /dev/video1 = 1, etc.)
CAMERA_RESOLUTION = (640, 480)
CAMERA_FRAMERATE = 30
LIVESTREAM_PORT = 8080

# ======================
# Roboflow Configuration (Autism Behavior Detection)
# ======================
# Model: https://universe.roboflow.com/asddetection/autism-ximav
# Classes (16): Aggressive_Behavior, Avoid_Eye_Contact, Covering_Ears, Finger_Bitting,
#               Finger_Flicking, Hand_Clapping, Hand_Flapping, Head_Banging, Holding_Item,
#               Jumping, SIB_Bitting, Shaking_Legs, Toe_Walking, Tpot_Stimming, Twirling,
#               Weird_Expression

ROBOFLOW_API_KEY = "bplvUh0xwWNAPCg8VJf2"  # Get from https://app.roboflow.com -> Settings -> API Keys
ROBOFLOW_MODEL_ID = "autism-ximav/1"  # Model ID from Roboflow
ROBOFLOW_CONFIDENCE_THRESHOLD = 0.5  # Minimum confidence to report detection (0.0-1.0)
BEHAVIOR_DETECTION_INTERVAL = 1.0  # Seconds between detection runs

# ======================
# Display Configuration
# ======================
# 2.4/2.8" SPI TFT LCD (ILI9341) - 240x320 with touch
DISPLAY_MODEL = "ILI9341"
SCREEN_WIDTH = 320
SCREEN_HEIGHT = 240
DISPLAY_SPI_SPEED = 32000000  # 32MHz SPI clock
DISPLAY_ROTATION = 0  # 0, 90, 180, 270

# ======================
# Microphone Configuration
# ======================
# INMP441 I2S MEMS Microphone
MIC_MODEL = "INMP441"
MIC_TYPE = "I2S"
MIC_SAMPLE_RATE = 16000
MIC_CHANNELS = 1
MIC_BIT_DEPTH = 24  # INMP441 outputs 24-bit audio

# ======================
# Noise Monitor Configuration (INMP441 I2S)
# ======================
# Enable environmental noise monitoring
NOISE_MONITOR_ENABLED = True
NOISE_MONITOR_DEVICE = "hw:sndrpigooglevoi,0"  # I2S microphone by name (stable across reboots)
NOISE_MONITOR_SAMPLE_RATE = 48000  # Hardware runs at 48kHz
NOISE_MONITOR_CHANNELS = 2  # I2S stereo (use left channel in software)
NOISE_MONITOR_FORMAT = "S32_LE"  # 32-bit signed little-endian
NOISE_MONITOR_PERIOD_SIZE = 1024  # Samples per read (~21ms at 48kHz)
NOISE_MONITOR_READ_INTERVAL = 1.0  # Seconds between noise level calculations
NOISE_MONITOR_ALERT_THRESHOLD = 70  # dB level for high noise alerts (lowered from 85 dB OSHA standard)
NOISE_MONITOR_SMOOTHING_WINDOW = 3  # Moving average window (reduce jitter)
NOISE_MONITOR_CALIBRATION_OFFSET = 0  # dB offset for calibration (+/- adjust)

# ======================
# Voice Command Configuration (Atom Echo)
# ======================
# Voice Input Configuration
VOICE_INPUT_TYPE = "sounddevice"    # Use sounddevice (webcam mic)
VOICE_MIC_DEVICE = 2                # Microphone device index (2 = webcam USB Audio)
                                    # Run: python -c "import sounddevice; print(sounddevice.query_devices())"

# Atom Echo USB Serial Connection (for TTS output)
VOICE_SERIAL_PORT = "/dev/ttyUSB0"  # USB serial port for Atom Echo speaker
VOICE_BAUD_RATE = 921600            # High baud rate for audio streaming
VOICE_SAMPLE_RATE = 16000           # 16kHz from Atom Echo (matches Vosk requirement)
VOICE_FRAME_SIZE = 480              # 30ms frame at 16kHz (480 samples)

# Wake Word Configuration
VOICE_WAKE_WORD = "orb"             # Wake word to activate voice commands
VOICE_COMMAND_TIMEOUT = 30          # Seconds to wait for command after wake word
VOICE_COMMANDS_ENABLED = True       # Enable/disable voice command execution (testing mode)

# Phonetic alternatives - words that sound like our target words
# Vosk might recognize these variations depending on pronunciation
VOICE_WAKE_WORD_ALTERNATIVES = [
    "orb", "orbs", "herb", "or", "all", "ball", "oral", "aura", "orbit"
]

# Voice Activity Detection (VAD)
VOICE_VAD_MODE = 1                  # 0-3, higher = more aggressive (try 1 for less sensitivity)
VOICE_VAD_FRAME_MS = 30             # Frame duration in ms (10, 20, or 30)

# Vosk Speech Recognition Model
VOICE_MODEL_PATH = "/home/abdul/fyp2/models/vosk-model"

# Limited vocabulary for Vosk (improves accuracy dramatically)
# Only these words will be recognized - add variations for robustness
VOICE_VOCABULARY = [
    # Wake word variations
    "orb", "orbs", "ball", "oral", "aura", "orbit",
    # Music command variations
    "music", "songs", "song", "play", "tune", "sound",
    # Anime command variations
    "anime", "animation", "cartoon", "video", "show",
    # Both command variations
    "both", "everything", "all",
    # Common words that might be spoken
    "stop", "cancel", "yes", "no", "hey", "hi", "hello", "please", "thank",
    # Unknown catch-all
    "[unk]"
]

# Voice Commands (keyword -> action)
# Maps recognized words to actions
VOICE_COMMANDS = {
    # Music variations
    "music": "play_music",
    "songs": "play_music",
    "song": "play_music",
    "play": "play_music",
    "tune": "play_music",
    "sound": "play_music",
    # Anime variations
    "anime": "play_animation",
    "animation": "play_animation",
    "cartoon": "play_animation",
    "video": "play_animation",
    "show": "play_animation",
    # Both variations
    "both": "play_both",
    "everything": "play_both",
}

# TTS Response Messages
VOICE_RESPONSE_READY = "I'm ready"
VOICE_RESPONSE_TIMEOUT = "Sorry, try again later"
VOICE_RESPONSE_UNKNOWN = "Sorry, I can't understand"
VOICE_RESPONSE_MUSIC = "Playing music"
VOICE_RESPONSE_ANIME = "Playing animation"
VOICE_RESPONSE_BOTH = "Playing music and animation"

# LED Commands for Atom Echo
VOICE_LED_OFF = "LED:OFF"
VOICE_LED_BLUE = "LED:BLUE"         # Ready for command
VOICE_LED_GREEN = "LED:GREEN"       # Processing
VOICE_LED_RED = "LED:RED"           # Error

# ======================
# Data Update Intervals (seconds)
# ======================
SENSOR_READ_INTERVAL = 2.0
ESP32_POLL_INTERVAL = 1.0
BLE_SEND_INTERVAL = 1.0

# ======================
# Live Streaming Configuration
# ======================
# Access Point Configuration (when streaming)
STREAM_AP_SSID = "CalmOrb-LIVE"
STREAM_AP_PASSWORD = "calmorb123"  # Fixed password for development (min 8 chars)
STREAM_AP_CHANNEL = 6
STREAM_AP_IP = "192.168.4.1"
STREAM_AP_NETMASK = "255.255.255.0"
STREAM_DHCP_START = "192.168.4.10"
STREAM_DHCP_END = "192.168.4.50"

# Video Streaming Configuration (MJPEG over HTTP)
STREAM_VIDEO_PORT = 8080
STREAM_VIDEO_RESOLUTION = (640, 480)
STREAM_VIDEO_FPS = 15
STREAM_VIDEO_QUALITY = 70  # JPEG quality 0-100

# Audio Streaming Configuration (WebSocket)
STREAM_AUDIO_PORT = 8081
STREAM_AUDIO_SAMPLE_RATE = 16000
STREAM_AUDIO_CHANNELS = 1
STREAM_AUDIO_CHUNK_SIZE = 1024  # Samples per chunk

# Streaming Timeouts
STREAM_TIMEOUT = 7200  # Max stream duration in seconds (2 hours - safety limit)
STREAM_CLIENT_TIMEOUT = 3600  # Disconnect if no client for this many seconds (1 hour)
STREAM_WIFI_RESTORE_RETRIES = 3  # Retries when restoring original Wi-Fi

# Streaming State Values (for BLE notifications)
STREAM_STATE_IDLE = 0
STREAM_STATE_PREPARING = 1
STREAM_STATE_READY = 2
STREAM_STATE_ACTIVE = 3
STREAM_STATE_STOPPING = 4
STREAM_STATE_ERROR = 5
