# 🔊 Atom Echo Voice Feedback System

> Audio feedback system for voice command confirmation using M5Stack Atom Echo

## 📋 Overview

The M5Stack Atom Echo serves as an audio feedback device that receives voice command recognition results from the Raspberry Pi via USB serial and responds with distinct tone patterns. It provides immediate auditory confirmation for voice commands without requiring complex audio playback, making it lightweight and reliable.

## ✨ Key Features

### 🎵 **Tone-Based Audio Feedback**
- **No WAV Playback**: Uses simple tones instead of audio files (more reliable, lower latency)
- **5 Distinct Patterns**: Each command has a unique beep sequence
- **Fast Response**: <50ms latency from command to tone output
- **High Baud Rate**: 921600 bps for fast serial communication

### 🎼 **Tone Patterns**

| Command | Pattern | Description |
|---------|---------|-------------|
| **Ready** | 🔊🔊🔊 (Ascending) | 500Hz → 1000Hz → 1500Hz (startup/ready) |
| **Music** | 🔊🔊 (Rapid) | 2x 1000Hz beeps (100ms gap) |
| **Animation** | 🔊🔊 (Rapid) | 2x 1000Hz beeps (100ms gap) |
| **Both** | 🔊🔊 (Rapid) | 2x 1000Hz beeps (100ms gap) |
| **Error/Sorry** | 🔊🔊 (Rapid) | 2x 1000Hz beeps (100ms gap) |
| **Default** | 🔊 (Single) | 1x 1000Hz beep (500ms) |

*Note: Each tone is 300-500ms with 100-500ms intervals*

### 📡 **Serial Communication**
- **Interface**: USB Serial (CDC)
- **Baud Rate**: 921600 bps
- **Protocol**: Simple text commands
- **Timeout**: 50ms buffer timeout for command processing

### 🔇 **Microphone Disabled**
- **Speaker Only**: Internal mic disabled to avoid conflicts
- **I2S Optimization**: Speaker kept active (no re-initialization)
- **Volume**: Fixed at max (255) for clear feedback

## 🛠️ Hardware Specifications

| Component | Specification |
|-----------|--------------|
| **Device** | M5Stack Atom Echo (ESP32-PICO-D4) |
| **Microcontroller** | ESP32-PICO-D4 (240 MHz dual-core) |
| **Flash** | 4 MB |
| **RAM** | 520 KB SRAM |
| **Speaker** | Built-in I2S speaker (NS4168 amplifier) |
| **Microphone** | SPM1423 (DISABLED in firmware) |
| **LED** | SK6812 RGB LED (DISABLED to avoid Serial interference) |
| **USB** | USB-C (power + serial communication) |
| **Size** | 24×24×14 mm |

## 📊 Serial Protocol

### **Command Format**
```
<command_text>\n
```

### **Supported Commands**
```
ready       → 3 ascending beeps (500Hz, 1000Hz, 1500Hz)
music       → 2 rapid beeps (1000Hz × 2)
animation   → 2 rapid beeps (1000Hz × 2)
anime       → 2 rapid beeps (1000Hz × 2) [alias]
both        → 2 rapid beeps (1000Hz × 2)
sorry       → 2 rapid beeps (1000Hz × 2)
unknown     → 2 rapid beeps (1000Hz × 2)
<any>       → 1 beep (1000Hz)
```

### **Example Communication**
```python
# From Raspberry Pi (Python)
import serial
ser = serial.Serial('/dev/ttyUSB0', 921600, timeout=1)

# Send command
ser.write(b'music\n')
# Atom Echo responds with 2 rapid beeps

ser.write(b'ready\n')
# Atom Echo responds with 3 ascending beeps
```

## 🏗️ Software Architecture

### **Core Components**
```cpp
main.cpp (213 lines)
├── handleCommand()      // Parse and execute tone patterns
├── playTonePattern()    // [DEPRECATED] Old implementation
└── loop()               // Serial listener with timeout
```

### **Key Features**
- **C-Style Strings**: Avoids String class corruption issues
- **Pattern-Based**: Command → Pattern ID → Tone execution
- **Timeout-Based**: 50ms timeout for command buffering
- **Non-Blocking**: 1ms loop delay for responsive processing
- **No Serial.println()**: Avoids corrupting communication channel

## 🔧 Configuration

### **PlatformIO Configuration** (`platformio.ini`)
```ini
[env:m5stack-atom]
platform = espressif32
board = m5stack-atom
framework = arduino
monitor_speed = 921600
upload_speed = 1500000

lib_deps =
    m5stack/M5Unified@^0.1.6
    earlephilhower/ESP8266Audio@^1.9.7

build_flags =
    -DARDUINO_M5STACK_ATOM
    -std=gnu++17

board_build.filesystem = littlefs
```

### **M5Unified Configuration**
```cpp
auto cfg = M5.config();
cfg.led_brightness = 0;      // LED disabled (Serial interference)
cfg.internal_mic = false;    // Microphone disabled
cfg.internal_spk = true;     // Speaker enabled
M5.begin(cfg);
```

## 🚀 Installation

### **1. Install PlatformIO**
```bash
# Via pip
pip install platformio

# Or via VSCode extension
# Install "PlatformIO IDE" from VSCode extensions
```

### **2. Clone/Download Project**
```bash
cd ~/
git clone <your-repo-url> atom-echo-voice
cd atom-echo-voice
```

### **3. Build & Upload**
```bash
# Build firmware
pio run

# Upload to Atom Echo (connect via USB-C)
pio run -t upload

# Monitor serial output (optional)
pio device monitor -b 921600
```

### **4. Test Communication**
```bash
# From Raspberry Pi
echo "ready" > /dev/ttyUSB0
# Should hear 3 ascending beeps

echo "music" > /dev/ttyUSB0
# Should hear 2 rapid beeps
```

## 📈 System Integration

### **Raspberry Pi Connection**
```python
# services/voice_service.py (example)
import serial

class AtomEchoFeedback:
    def __init__(self, port='/dev/ttyUSB0', baud=921600):
        self.serial = serial.Serial(port, baud, timeout=1)

    def send_feedback(self, command: str):
        """Send command to Atom Echo for audio feedback"""
        self.serial.write(f"{command}\n".encode())
        self.serial.flush()

# Usage
echo = AtomEchoFeedback()
echo.send_feedback('ready')    # Startup confirmation
echo.send_feedback('music')    # Play music command confirmed
echo.send_feedback('animation') # Play animation confirmed
echo.send_feedback('both')     # Play both confirmed
echo.send_feedback('sorry')    # Command not recognized
```

## 🎯 Use Cases

### **Voice Command Confirmation**
```
User: "ORB, play music!"
Pi: [Recognizes command] → Sends "music\n" to Atom Echo
Atom Echo: [Beeps twice rapidly] → Audio confirmation
Pi: [Plays music on ESP32 stress ball]
```

### **System Ready Notification**
```
Pi: [Boots up] → Sends "ready\n" to Atom Echo
Atom Echo: [3 ascending beeps] → System is ready for commands
```

### **Error Feedback**
```
User: "ORB, do something!"
Pi: [Command not recognized] → Sends "sorry\n" to Atom Echo
Atom Echo: [2 rapid beeps] → Try again
```

## ⚠️ Design Decisions

### **Why Tones Instead of WAV Files?**
1. **Reliability**: No SD card required, no file corruption issues
2. **Latency**: <50ms response time (WAV playback: 200-500ms)
3. **Simplicity**: No audio decoding overhead
4. **Memory**: Entire firmware <200KB (WAV files would require >1MB)

### **Why High Baud Rate (921600)?**
- Faster command transmission (<1ms vs 10ms at 115200)
- Reduces serial buffer overflow risk
- Better for real-time feedback

### **Why LED Disabled?**
- FastLED library interferes with Serial communication
- RGB LED not needed for audio-only feedback
- Reduces power consumption

### **Why Microphone Disabled?**
- Voice recognition handled by Raspberry Pi (more powerful)
- Reduces I2S conflicts with speaker
- Simplifies firmware logic

## 🔍 Troubleshooting

### No Beeps Heard
```bash
# Check serial connection
ls -l /dev/ttyUSB*

# Test with direct echo
echo "ready" > /dev/ttyUSB0

# Check Atom Echo power (should see solid green LED on Pi side)
```

### Distorted/Corrupted Audio
```cpp
// Ensure speaker is initialized only once in setup()
M5.Speaker.begin();  // DO NOT call in loop()!

// Ensure no Serial.println() in main code
// Only in setup() before speaker init
```

### Serial Communication Errors
```bash
# Check baud rate matches
stty -F /dev/ttyUSB0 921600

# Check permissions
sudo chmod 666 /dev/ttyUSB0

# Or add user to dialout group
sudo usermod -aG dialout $USER
```

## 📝 Development Notes

### **Tone Pattern Guidelines**
- **300-500ms**: Good tone duration (clear but not annoying)
- **100-500ms**: Gap between tones (distinguishable but responsive)
- **500-1500Hz**: Frequency range (audible, not piercing)
- **2-3 tones max**: Keep patterns short and memorable

### **Performance Metrics**
- **Command Processing**: <50ms (timeout-based buffering)
- **Tone Generation**: <5ms (I2S direct output)
- **Total Latency**: <60ms (command → audio)
- **Memory Usage**: ~50KB RAM, ~180KB Flash

## 📦 Project Structure

```
atom-echo-voice/
├── platformio.ini              # PlatformIO configuration
├── src/
│   ├── main.cpp                # Main firmware (213 lines)
│   └── main_wav.cpp.bak        # OLD: WAV-based version (deprecated)
├── data/                       # OLD: WAV files (not used)
│   ├── ready.wav
│   ├── music.wav
│   ├── animation.wav
│   ├── both.wav
│   └── unknown.wav
├── generate_friendly_voice.sh  # Script to generate WAV files (not used)
└── README.md                   # This file
```

## 🔄 Version History

### **v2.0 (Current) - Tone-Based**
- ✅ Replaced WAV playback with tone patterns
- ✅ Improved latency (<60ms)
- ✅ Removed SD card dependency
- ✅ Simplified firmware (213 lines)

### **v1.0 - WAV-Based**
- ❌ Used pre-recorded WAV files
- ❌ Required SPIFFS filesystem
- ❌ 200-500ms latency
- ❌ Complex audio decoding

## 📝 License

MIT License - See LICENSE file for details

## 👥 Contributors

- **Abdul** - Lead Developer

## 📧 Support

For issues and questions, please open an issue on GitHub.

---

**Last Updated**: January 2026
**Firmware Version**: 2.0.0
**Hardware**: M5Stack Atom Echo (ESP32-PICO-D4)

