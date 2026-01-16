# 🎯 Stress Ball Monitoring Hub - Raspberry Pi System

> Real-time autism child stress monitoring system using ESP32 stress ball, environmental sensors, and AI behavior detection

## 📋 Overview

The Raspberry Pi acts as the central hub for monitoring child stress levels and environmental conditions. It receives sensor data from an ESP32-powered stress ball via UDP, monitors environmental noise, tracks proximity using BLE beacons, and provides real-time behavior analysis through camera vision AI.

## ✨ Key Features

### 🔴 **Core Monitoring**
- **ESP32 Stress Ball Integration**: Receives grip pressure (PSI) and motion data via UDP
- **BLE GATT Server**: Multi-connection support for mobile app communication
- **Distress Detection**: Identifies 3-grip patterns and consecutive motion alerts
- **TFT Display Control**: Plays calming animations (5 GIF options) on 2.8" ILI9341 display

### 🌡️ **Environmental Monitoring**
- **Noise Level Detection**: INMP441 I2S microphone measures ambient noise (dB SPL)
- **Temperature & Humidity**: DHT22 sensor tracks environmental conditions
- **Alert System**: Immediate notifications when noise exceeds 70 dB threshold

### 📹 **AI Behavior Analysis**
- **Camera Detection**: USB webcam with Roboflow AI model (autism-ximav/1)
- **16 Behavior Types**: Detects behaviors like hand-flapping, rocking, spinning, etc.
- **Real-time Processing**: ~2 FPS analysis with confidence scoring

### 📡 **Proximity Tracking**
- **BLE Beacon Scanning**: Monitors ESP32 beacon RSSI for distance estimation
- **4 Proximity Zones**: NEAR (<15m), MEDIUM (15-25m), FAR (25-35m), OUT_OF_RANGE (>35m)
- **Optimized Scanning**: 97% scan coverage (3s scan / 3.1s cycle) to catch intermittent beacons

### 🎥 **Live Streaming**
- **WiFi AP Mode**: Creates hotspot for mobile app video streaming
- **MJPEG Video**: Real-time camera feed at http://192.168.4.1:8080/video
- **WebSocket Audio**: Audio streaming (when available) at ws://192.168.4.1:8081

### 🎙️ **Voice Commands**
- **Wake Word**: "ORB!" activation
- **Commands**: Play music, play animation, play both
- **Audio Feedback**: Confirmation via speaker/buzzer

## 🛠️ Hardware Components

| Component | Model | Purpose | Interface |
|-----------|-------|---------|-----------|
| **SBC** | Raspberry Pi 4/5 | Main controller | - |
| **Display** | ILI9341 2.8" TFT | Calming animations | SPI |
| **Microphone** | INMP441 I2S | Environmental noise | I2S (hw:sndrpigooglevoi,0) |
| **Temperature** | DHT22 | Temp & humidity | GPIO 4 |
| **Camera** | USB Webcam | Behavior detection | USB (device 0) |
| **WiFi** | Built-in | ESP32 communication | UDP 4210, AP mode |
| **Bluetooth** | Built-in (hci0) | Mobile app + proximity | BLE GATT + Scanner |

## 📊 Communication Protocols

### **BLE GATT Service** (Peripheral Role)
- **Service UUID**: `12345678-1234-5678-1234-56789abcdef0`
- **Characteristics**:
  - `...def1`: Settings (R/W) - Animation, sound, volume, profile
  - `...def2`: Commands (W) - Control commands (binary protocol)
  - `...def3`: Status (R/N) - Hub status, streaming info
  - `...def4`: Sensor Data (R/N) - Pressure, temp, motion, noise, proximity
  - `...def5`: Behavior Data (R/N) - AI camera detections

### **UDP Communication** (WiFi)
- **ESP32 → Pi**: Port 4210 (sensor data broadcast every ~1s)
- **Pi → ESP32**: 192.168.4.1:5006 (volume, sound commands)

### **BLE Beacon Scanning** (Central Role)
- **Target Device**: "ESP32-StressBall"
- **Scan Interval**: 0.1s between scans
- **Scan Duration**: 3.0s per scan
- **Lost Timeout**: 25s before marking OUT_OF_RANGE

## 🏗️ Software Architecture

### **Main Services** (`services/`)
```
main_service.py          # Core orchestrator (async event loop)
├── ble_service.py       # GATT server (mobile app communication)
├── ble_beacon_service.py # Proximity scanner (ESP32 tracking)
├── distress_service.py  # UDP listener + TFT display control
├── camera_service.py    # AI behavior detection (Roboflow)
├── sensor_service.py    # DHT22 temperature/humidity
├── noise_monitor_service.py # I2S microphone (dB SPL)
├── streaming_service.py # Video/audio streaming (AP mode)
└── voice_service.py     # Voice command recognition
```

### **Key Features**
- **Async Python**: Non-blocking I/O with asyncio
- **Child Profile System**: Optional services start only when paired (privacy + power saving)
- **Multi-Connection BLE**: No bonding/pairing required (Samsung S23 compatible)
- **Service Lifecycle**: Managed by systemd (`distress.service`)

## 🔧 Configuration

### **Core Settings** (`config/settings.py`)
```python
# Noise Monitoring
NOISE_MONITOR_DEVICE = "hw:sndrpigooglevoi,0"  # Stable card name
NOISE_MONITOR_ALERT_THRESHOLD = 70  # dB level for alerts

# BLE Beacon (Proximity)
BEACON_SCAN_INTERVAL = 0.1   # Fast scanning
BEACON_SCAN_DURATION = 3.0   # Longer window
BEACON_LOST_TIMEOUT = 25.0   # Tolerant timeout

# ESP32 Communication
ESP32_IP = "192.168.4.1"
UDP_LISTEN_PORT = 4210
ESP32_CMD_PORT = 5006
```

### **BLE Commands** (Binary Protocol)
```
0x01 - Set Animation (param: 1-5)
0x02 - Set Sound (param: 1-13)
0x03 - Find My Device (alarm on ESP32)
0x04 - Enable/Disable Animation (param: 0/1)
0x05 - Enable/Disable Sound (param: 0/1)
0x06 - Stop Sound
0x07 - Get Settings
0x08 - Play Sound (param: 1-14)
0x09 - Play Animation (param: 1-5)
0x0A - Set Volume (param: 0-30)
0x10 - Start Live Stream
0x11 - Stop Live Stream
0x12 - Get Stream Status
0x13 - Get AP Credentials
0x14 - Set Child Profile (param: 0=off, 1=on)
```

## 🚀 Installation

### **1. System Dependencies**
```bash
sudo apt update
sudo apt install -y python3-pip python3-venv libasound2-dev i2c-tools
```

### **2. Python Environment**
```bash
cd /home/abdul/fyp2
python3 -m venv ~/tftenv
source ~/tftenv/bin/activate
pip install -r requirements.txt
```

### **3. Enable Hardware**
```bash
# Enable I2C (for MPU6050 if used)
sudo raspi-config nonint do_i2c 0

# Enable I2S (INMP441 microphone)
# Add to /boot/firmware/config.txt:
dtoverlay=i2s-mmap
dtoverlay=googlevoicehat-soundcard

# Reboot
sudo reboot
```

### **4. Start Service**
```bash
sudo systemctl enable distress.service
sudo systemctl start distress.service
sudo journalctl -u distress.service -f
```

## 📈 System Requirements

- **OS**: Raspberry Pi OS (64-bit recommended)
- **Python**: 3.9+ (3.13 tested)
- **RAM**: 2GB minimum (4GB recommended for camera AI)
- **Storage**: 8GB+ SD card
- **Network**: WiFi required (ESP32 AP: 192.168.4.x)

## 🔍 Monitoring & Logs

```bash
# Real-time logs
sudo journalctl -u distress.service -f

# Check specific service
sudo journalctl -u distress.service -n 100 | grep "NoiseMonitor"
sudo journalctl -u distress.service -n 100 | grep "BLE Beacon"

# System status
sudo systemctl status distress.service
```

## ⚠️ Known Limitations

- **Audio Streaming**: Not working (I2S conflict with noise monitor)
- **ESP32 Connection**: Drops during Pi AP mode for video streaming (UDP lost until streaming ends)
- **Camera FPS**: Limited to ~2 FPS due to Roboflow API latency
- **I2S Device**: Single I2S interface (noise monitor OR audio streaming, not both)

## 🐛 Troubleshooting

### Noise Monitor Shows 0.0 dB
```bash
# Check I2S device
arecord -l
cat /proc/asound/cards

# Restart service
sudo systemctl restart distress.service
```

### BLE Not Discoverable
```bash
bluetoothctl
power on
discoverable on
pairable off
quit
```

### ESP32 Not Sending Data
```bash
# Check UDP traffic
sudo journalctl -u distress.service -f | grep UDP

# Verify network
ping 192.168.4.1
```

## 📝 License

MIT License - See LICENSE file for details

## 👥 Contributors

- **Abdul Hanif** - Developer

## 📧 Support

For issues and questions, please open an issue on GitHub.

---

**Last Updated**: January 2026
**Version**: 2.0.0

