# 🌟 CalmOrb IoT System

> **Emotional Support Technology for Children with Autism**  
> A smart, interactive system combining AI-powered behavior detection with calming sensory feedback

[![Hardware](https://img.shields.io/badge/Platform-Raspberry%20Pi%204-red.svg)](https://www.raspberrypi.org/)
[![Hardware](https://img.shields.io/badge/Hardware-ESP32-green.svg)](https://www.espressif.com/)

---

## 👋 Welcome!

Thank you for your interest in the **CalmOrb** project! This repository contains the complete IoT system configuration for an emotional regulation toy designed to help children with autism manage stress, anxiety, and emotional breakdowns.

### 📚 About This Project

CalmOrb is a Final Year Project (FYP) developed at the **University of Malaya** under the supervision of **Dr. Nazean Binti Jomhari**. The system combines:

- 🎯 **Smart Stress Ball** (ESP32-based) with pressure and motion sensors
- 🖥️ **Raspberry Pi Hub** with camera, microphone, and environmental monitoring
- 📱 **Mobile Application** for real-time monitoring and caregiver control

**Research Focus:** Designing assistive technology that helps autistic children regulate emotions through real-time distress detection, calming interventions (music, animations, vibrations), and caregiver alerts.

---

## ⚠️ Important Notice

### 📖 Open Source & Academic Use

This repository is **publicly available** for:
- ✅ Educational purposes and academic research
- ✅ Personal learning and experimentation
- ✅ Inspiration for similar assistive technology projects

### 🚫 Usage Restrictions

**Please DO NOT:**
- ❌ Use this code commercially without permission
- ❌ Claim this work as your own in academic submissions
- ❌ Redistribute without proper attribution
- ❌ Deploy in production environments without thorough testing and ethical approval

### 📜 Ethical Considerations

This project involves:
- **Children with special needs** (autism spectrum disorder)
- **Sensitive behavioral and biometric data**
- **Camera and audio recordings**

If you plan to use or adapt this system:
1. **Obtain proper ethics approval** from your institution's IRB/ethics committee
2. **Secure informed consent** from parents/guardians
3. **Comply with data protection regulations** (GDPR, COPPA, PDPA)
4. **Implement robust data security and privacy measures**

### 🙏 Citation

If you use this work in your research or project, please cite:

```bibtex
@mastersthesis{hanif2026calmorb,
  title={Designing Emotional Breakdown Toys for Children with Autism},
  author={Abdul Hanif Bin Abdul Aziz and Abdul Azim Bin Abdul Salam},
  year={2026},
  school={University of Malaya},
  supervisor={Dr. Nazean Binti Jomhari}
}
```

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         CALMORB SYSTEM                          │
└─────────────────────────────────────────────────────────────────┘

┌──────────────────────┐      ┌──────────────────────┐      ┌──────────────────────┐
│   ESP32 Stress Ball  │◄────►│   Raspberry Pi Hub   │◄────►│   Mobile App         │
│                      │ BLE  │                      │ BLE  │                      │
│ • Pressure Sensor    │      │ • Pi Camera (YOLOv8) │      │ • React Native       │
│ • MPU6050 (Motion)   │      │ • ATOM Echo (Audio)  │      │ • Real-time Monitor  │
│ • NeoPixel LEDs      │      │ • DHT22 (Temp)       │      │ • Remote Control     │
│ • Vibration Motor    │      │ • I2S Microphone     │      │ • Alerts & History   │
└──────────────────────┘      │ • Speaker (Music)    │      └──────────────────────┘
                              └──────────────────────┘
```

### Communication Protocols

| Protocol | Purpose | Components |
|----------|---------|------------|
| **BLE (Bluetooth Low Energy)** | Primary communication | ESP32 ↔ Pi, Pi ↔ Mobile App |
| **UDP (User Datagram Protocol)** | Beacon broadcasting | ESP32 → Pi (location tracking) |
| **WiFi** | Configuration mode | Pi ↔ Mobile App (initial setup) |
| **I2S** | Audio streaming | ATOM Echo ↔ Pi |

---

## 🔧 Hardware Components

### 1️⃣ **ESP32 Stress Ball** (Smart Squeeze Toy)

| Component | Model | Purpose |
|-----------|-------|---------|
| **Microcontroller** | ESP32-WROOM-32 | Main processor |
| **Pressure Sensor** | FlexiForce A201 | Detects squeeze intensity |
| **Motion Sensor** | MPU6050 (IMU) | Detects shaking/throwing |
| **LED Ring** | WS2812B NeoPixel (16 LEDs) | Visual feedback |
| **Vibration Motor** | 3V DC Motor | Haptic feedback |
| **Battery** | 3.7V 2000mAh LiPo | Portable power |

**Firmware:** Arduino/PlatformIO (C++)  
**Key Features:** Real-time distress detection, autonomous calming mode, low-power sleep

---

### 2️⃣ **Raspberry Pi Hub** (Central Intelligence)

| Component | Model | Purpose |
|-----------|-------|---------|
| **Main Board** | Raspberry Pi 4 Model B (4GB) | Main processor |
| **Camera** | Pi Camera Module v2 (8MP) | Facial emotion detection |
| **Smart Speaker** | M5Stack ATOM Echo | Voice commands + audio streaming |
| **Temperature Sensor** | DHT22 | Environmental monitoring |
| **I2S Microphone** | INMP441 | Noise level detection |
| **Power Supply** | 5V 3A USB-C | Continuous power |

**OS:** Raspberry Pi OS (Debian-based)  
**Key Features:** YOLOv8 behavior recognition (16 classes), BLE GATT server, audio playback

---

### 3️⃣ **Mobile Application** (Caregiver Interface)

**Platform:** React Native (Expo)  
**Supported OS:** Android 8.0+, iOS 13.0+

**Key Features:**
- 📊 Real-time dashboard (pressure, motion, behavior, environment)
- 🎵 Remote control (play music, trigger animations, vibrations)
- 🔔 Push notifications (distress alerts, high noise warnings)
- 📅 Routine scheduling (e.g., "Play calming music at 8 PM daily")
- 📖 Session history and behavioral logs

---

## 🚀 Quick Start Guide

### Prerequisites

- **Hardware:**
  - ✅ ESP32 development board
  - ✅ Raspberry Pi 4 (4GB recommended)
  - ✅ M5Stack ATOM Echo
  - ✅ Pi Camera Module v2
  - ✅ Sensors (FlexiForce, MPU6050, DHT22, INMP441)
  
- **Software:**
  - ✅ PlatformIO (for ESP32)
  - ✅ Python 3.9+ (for Raspberry Pi)
  - ✅ Node.js 18+ & Expo CLI (for mobile app)

---

### 1️⃣ ESP32 Configuration

```bash
# Clone repository
git clone https://github.com/YOUR_USERNAME/CalmOrbIoT.git
cd CalmOrbIoT/esp32

# Install PlatformIO
pip install platformio

# Configure WiFi credentials (optional, for OTA updates)
# Edit src/config.h
nano src/config.h

# Build and upload firmware
pio run --target upload

# Monitor serial output
pio device monitor
```

**Key Configuration:**
- **BLE Name:** `"CalmOrb_ESP_XXXX"` (auto-generated from MAC address)
- **Pressure Threshold:** 500 units (adjustable in code)
- **Motion Threshold:** 5000 units (aggressive movement)
- **LED Colors:** Configurable emotion mapping

---

### 2️⃣ Raspberry Pi Setup

```bash
# 1. Update system
sudo apt update && sudo apt upgrade -y

# 2. Install system dependencies
sudo apt install -y python3-pip python3-venv \
    bluetooth bluez libbluetooth-dev \
    portaudio19-dev libatlas-base-dev \
    libopencv-dev libcap-dev

# 3. Clone and setup project
cd ~
git clone https://github.com/YOUR_USERNAME/CalmOrbIoT.git
cd CalmOrbIoT/raspberry_pi

# 4. Create virtual environment
python3 -m venv tftenv
source tftenv/bin/activate

# 5. Install Python dependencies
pip install -r requirements.txt

# 6. Download YOLOv8 model
# Place your trained model in models/yolov8n_autism_v1.pt

# 7. Configure Bluetooth permissions
sudo setcap 'cap_net_raw,cap_net_admin+eip' $(which python3)

# 8. Setup systemd service (auto-start on boot)
sudo cp distress.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable distress.service
sudo systemctl start distress.service

# 9. Check service status
sudo systemctl status distress.service
sudo journalctl -u distress.service -f
```

**Configuration Files:**
- **Main config:** `services/config.json` (BLE UUIDs, service settings)
- **Audio files:** Place MP3s in `assets/audio/`
- **Video files:** Place MP4s in `assets/videos/`

**Bluetooth Pairing:**
```bash
# Enable Pi's Bluetooth
sudo bluetoothctl
[bluetooth]# power on
[bluetooth]# discoverable on
[bluetooth]# pairable on
```

---

### 3️⃣ Mobile App Setup

```bash
# Navigate to mobile app directory
cd CalmOrbIoT/mobile_app

# Install Node.js dependencies
npm install

# Start Expo development server
npx expo start

# Run on Android (requires Android Studio or physical device)
npx expo run:android

# Run on iOS (requires Xcode on macOS)
npx expo run:ios
```

**Configuration:**
- **BLE UUIDs:** Must match Raspberry Pi's UUIDs (in `src/hooks/useBLE.tsx`)
- **Permissions:** Enable Bluetooth, Location, Notifications

**First-Time Setup:**
1. Open app → **"Pair New Device"**
2. Scan for `"CalmOrb_Pi_XXXX"`
3. Connect (may require PIN: `0000`)
4. Wait for data synchronization

---

## 📡 BLE Communication Protocol

### Service UUIDs

| Service | UUID | Description |
|---------|------|-------------|
| **Main Service** | `12345678-1234-5678-1234-56789abcdef0` | Primary GATT service |
| **Sensor Data** | `12345678-1234-5678-1234-56789abcdef1` | Pressure & motion |
| **Behavior Data** | `12345678-1234-5678-1234-56789abcdef2` | AI-detected behaviors |
| **Environment Data** | `12345678-1234-5678-1234-56789abcdef3` | Temperature & noise |
| **Control Commands** | `12345678-1234-5678-1234-56789abcdef4` | Write actions (play music, etc.) |

### Data Format (JSON)

**Sensor Data Packet:**
```json
{
  "type": "sensor",
  "deviceId": "ESP32_XXXX",
  "timestamp": 1705484923,
  "pressure": 450,
  "motionX": 120,
  "motionY": -45,
  "motionZ": 980,
  "battery": 78
}
```

**Behavior Detection Packet:**
```json
{
  "type": "behavior",
  "deviceId": "Pi_XXXX",
  "timestamp": 1705484925,
  "behavior": "tantrum",
  "confidence": 0.87,
  "boundingBox": [120, 80, 400, 500]
}
```

**Control Command:**
```json
{
  "action": "play_music",
  "track": "calming_piano.mp3",
  "volume": 0.7
}
```

---

## 🧠 AI Behavior Detection

### Model: YOLOv8n (Custom-trained)

**Training Dataset:**
- 16 behavior classes (tantrum, hand-flapping, rocking, etc.)
- 5,000+ labeled images from autism research datasets
- Data augmentation (rotation, brightness, occlusion)

**Performance Metrics:**
- **Accuracy:** 84.2% (validation set)
- **mAP@0.5:** 0.78
- **Inference Speed:** ~15 FPS (on Raspberry Pi 4)

**Detected Behaviors:**
1. 😤 Tantrum (screaming, aggressive movement)
2. 🤚 Hand-flapping (repetitive hand motion)
3. 🪑 Rocking (back-and-forth body motion)
4. 🙈 Self-harm indicators (head-banging, biting)
5. 😰 Distress facial expressions
6. 😊 Calm/happy states
7. ... (10 more classes)

**Model Location:** `raspberry_pi/models/yolov8n_autism_v1.pt`

---

## 🎵 Sensory Feedback System

### Calming Interventions

| Intervention | Hardware | Trigger Condition |
|--------------|----------|-------------------|
| **Music Playback** | Pi speaker | Pressure > 500 OR behavior = "tantrum" |
| **Calming Animation** | NeoPixel LEDs | Motion > 5000 OR voice command "play animation" |
| **Haptic Vibration** | ESP32 motor | User-initiated via app |
| **Visual Feedback** | LED color change | Different emotions (red=distress, blue=calm) |

**Audio Library:**
- `calming_piano.mp3` (4 minutes)
- `nature_sounds.mp3` (ocean waves, 10 minutes)
- `white_noise.mp3` (continuous)

**LED Animations:**
- **Breathing Effect:** Slow fade in/out (calming)
- **Rainbow Cycle:** Full spectrum rotation (engaging)
- **Pulse Wave:** Quick pulses (alert)

---

## 🛡️ Security & Privacy

### Data Protection Measures

1. **Local Processing:** All AI inference runs on-device (no cloud upload)
2. **Encrypted BLE:** Pairing required, data encrypted during transmission
3. **No Persistent Storage:** Camera feed not recorded (live stream only)
4. **Anonymized Logs:** Device IDs hashed, no personal identifiers
5. **Parent Control:** All features require app authentication

### Known Limitations

⚠️ **This is a research prototype, NOT a medical device:**
- No clinical validation or FDA approval
- Not suitable for unsupervised use
- Requires adult supervision at all times
- Should NOT replace professional therapy

---

## 🧪 Testing & Validation

### Unit Tests

```bash
# Run ESP32 tests (PlatformIO)
cd esp32
pio test

# Run Pi service tests (pytest)
cd raspberry_pi
pytest tests/
```

### System Integration Tests

See `raspberry_pi/tests/integration/` for:
- BLE connection stability test
- Sensor data accuracy test
- Behavior detection performance test
- Audio latency test

**Test Results (Latest Run):**
- ✅ BLE connection success rate: 98%
- ✅ Sensor update frequency: 10 Hz (target: 10 Hz)
- ✅ Behavior detection latency: 150ms (target: <200ms)
- ✅ Audio playback latency: 0.8s (target: <1s)

---

## 🐛 Troubleshooting

### Common Issues

**1. ESP32 not appearing in BLE scan:**
- ✅ Check battery charge (must be >20%)
- ✅ Reset ESP32 (hold button for 3 seconds)
- ✅ Re-upload firmware with correct BLE name

**2. Raspberry Pi service not starting:**
```bash
# Check logs
sudo journalctl -u distress.service -n 50

# Common fixes:
sudo systemctl restart bluetooth
sudo systemctl restart distress.service
```

**3. Mobile app not receiving data:**
- ✅ Ensure Bluetooth and Location permissions granted
- ✅ Check BLE UUIDs match (Pi vs app config)
- ✅ Try disconnecting and reconnecting

**4. YOLOv8 model not loading:**
- ✅ Verify model file exists: `models/yolov8n_autism_v1.pt`
- ✅ Check file permissions: `chmod 644 models/*.pt`
- ✅ Install torch: `pip install torch torchvision`

---

## 📊 Performance Benchmarks

### Resource Usage (Raspberry Pi 4)

| Metric | Idle Mode | Active Monitoring |
|--------|-----------|-------------------|
| **CPU Usage** | 8% | 45% |
| **RAM Usage** | 450 MB | 1.2 GB |
| **Temperature** | 48°C | 62°C |
| **Power Draw** | 2.5W | 4.8W |

### Battery Life (ESP32 Stress Ball)

| Mode | Duration |
|------|----------|
| **Active Mode** (10 Hz updates) | ~8 hours |
| **Idle Mode** (sleep enabled) | ~24 hours |
| **Deep Sleep** | ~2 weeks |

---

## 🤝 Contributing

We welcome contributions from the community! However, please note:

### How to Contribute

1. **Fork** this repository
2. **Create a feature branch:** `git checkout -b feature/amazing-improvement`
3. **Commit changes:** `git commit -m "Add amazing improvement"`
4. **Push to branch:** `git push origin feature/amazing-improvement`
5. **Open a Pull Request**

### Contribution Guidelines

- ✅ Follow existing code style (use linters/formatters)
- ✅ Add unit tests for new features
- ✅ Update documentation (README, comments)
- ✅ Respect ethical guidelines (no data misuse)

**Priority Areas:**
- 🔧 Hardware improvements (better sensors, battery life)
- 🧠 AI model improvements (more behavior classes, higher accuracy)
- 📱 Mobile app UX enhancements
- 🌍 Localization (support for more languages)

---

## 📄 License

This project is licensed under the **MIT License** - see [LICENSE](LICENSE) file for details.

**Summary:** You may freely use, modify, and distribute this code with proper attribution. Commercial use requires permission from the authors.

---

## 📞 Contact & Support

### Authors

- **Abdul Hanif Bin Abdul Aziz** ([@Nipz652](https://github.com/Nipz652))  
  - Role: IoT System Development

- **Abdul Azim Bin Abdul Salam**  
  - Role: Mobile Application Development
  - GitHub: https://github.com/ImAzimm/Calm-Orb-Mobile-Apps

### Supervisor

- **Dr. Nazean Binti Jomhari**  
  - University of Malaya, Faculty of Computer Science & IT

### Please Support

---

## 🙌 Acknowledgments

We would like to thank:

- **University of Malaya** for project funding and facilities
- **Dr. Nazean Binti Jomhari** for invaluable guidance
- **Xing Yiming** (collaborator)
- **Parents and caregivers** who participated in user testing
- **Autism support organizations** in Malaysia 

### Special Thanks

- **Raspberry Pi Foundation** for documentation and community support
- **Espressif Systems** for ESP32 resources
- **Ultralytics** for YOLOv8 framework
- **Open-source community** for libraries and tools

---

## 📚 References & Further Reading

### Academic Papers

1. Cañete, R., & Peralta, M. E. (2022). ASDesign: A User-Centered Method for Assistive Technology for Autism. *Sustainability*, 14(1), 516.
2. Baron-Cohen, S. (1991). Do people with autism understand what causes emotion? *Child Development*, 62(2), 385–395.
3. Van den Boogert et al. (2021). Sensory processing and emotion regulation in children with autism. *Research in Developmental Disabilities*, 112, 103891.

### Related Projects

- [Project Tango](https://en.wikipedia.org/wiki/Tango_(platform)) - Google's spatial computing
- [OpenBCI](https://openbci.com/) - Open-source neuroscience tools
- [Affectiva](https://www.affectiva.com/) - Emotion AI for autism research

---

<div align="center">

## 💙 Supporting Autism Awareness

**1 in 36 children** are diagnosed with autism spectrum disorder.  
Let's build technology that empowers, not excludes.

---

**⭐ If you find this project helpful, please consider starring the repository!**

Made with ❤️ for the autism community

</div>
