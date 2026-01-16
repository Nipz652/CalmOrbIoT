# ESP32 Stress Ball System - Technical Summary

## Overview

The ESP32 Stress Ball is an intelligent sensory device designed for autism tantrum detection and intervention. It monitors grip pressure and motion patterns to detect escalating stress levels in children, providing real-time data to caregivers and triggering calming audio/visual feedback when needed.

## Hardware Components

### Core Components
- **Microcontroller**: ESP32 Dev Module (240MHz dual-core, 320KB RAM)
- **Pressure Sensors**: 2× Force Sensitive Resistors (FSR402, 20mm² active area)
- **Motion Sensor**: MPU6050 6-axis IMU (3-axis accelerometer + 3-axis gyroscope)
- **Audio Module**: DFPlayer Mini MP3 player with SD card
- **Communication**: WiFi (AP mode) + BLE beacon

### Pin Configuration
```
FSR Sensors:
  - FSR1: GPIO 34 (ADC1_CH6)
  - FSR2: GPIO 35 (ADC1_CH7)

DFPlayer Audio:
  - TX: GPIO 26
  - RX: GPIO 27
  - Baud: 9600

MPU6050 IMU:
  - SDA: GPIO 21
  - SCL: GPIO 22
  - I2C: 400kHz
```

## Key Features

### 1. Multi-Level Pressure Detection
Converts FSR voltage to PSI using voltage divider circuit (10kΩ resistor):

| Grip State | PSI Threshold | Meaning |
|-----------|---------------|---------|
| **None** | < 0.1 PSI | No contact |
| **Calm** | 0.1 - 0.5 PSI | Relaxed holding |
| **Moderate** | 0.5 - 4.0 PSI | Mild anxiety |
| **Stressed** | 4.0 - 8.0 PSI | Elevated stress |
| **Tantrum** | > 16.0 PSI | Meltdown state |

**Technical Details:**
- 12-bit ADC resolution (0-4095)
- 5 samples averaged per reading (reduced for BLE performance)
- 0.5ms delay between samples
- Voltage divider: `PSI = (V_FSR / R_FSR) / FSR_AREA`

### 2. Advanced Motion Detection

Seven distinct motion patterns calibrated for ball toy usage:

| Motion Type | Threshold | Description |
|------------|-----------|-------------|
| **Impact** | 38,000 | Hard throw/slam detection |
| **Bounce** | 28,000 (3 in 1s) | Repeated bouncing |
| **FreeFall** | < 1,500 (150ms) | Dropping/tossing |
| **ViolentShake** | 15,000 Δ (12 times) | Aggressive shaking |
| **Spinning** | 25,000 (500ms sustained) | Rotation around Z-axis |
| **Rocking** | 12,000 tilt (4 crosses) | Side-to-side rocking |
| **Tremble** | 6,000-14,000 Δ (18 in 800ms) | Fine trembling motion |

**Motion Thresholds Tuning:**
- All thresholds increased 40-150% from defaults for ball toy reliability
- Prevents false positives from normal handling
- Requires significant intentional motion to trigger

### 3. Pattern-Based Alerts

**5-Grip Pattern Detection:**
- Triggers when **5 grips > 8.0 PSI** detected
- Maximum **1 second gap** allowed between releases
- Calculates **dominant grip type** (Tantrum if ≥2 grips are Tantrum-level)
- Resets sequence if gap exceeds timeout
- Alert: `alert:PATTERN_3GRIP,dominant_type:Stressed`

**5-Motion Consecutive Detection:**
- Triggers when **same motion detected 5 times consecutively**
- Motion must be identical (e.g., 5× Impact, 5× Tremble)
- Resets counter when motion type changes
- Alert: `alert:MOTION_3X,motion_type:Impact`

**Behavior:**
- Single grips/motions: Silent (no audio/animation)
- Pattern completion: Audio playback + visual animation + UDP alert

### 4. Data Aggregation (5-Second Windows)

**Periodic Updates (Every 5 seconds):**
- **Motion**: Most frequent motion (excludes "None" unless no other motion)
- **PSI**: Average PSI across 250 samples over 5 seconds
- **Purpose**: Prevents spamming UDP with hundreds of "None" readings

**Immediate Alerts (On distress):**
- **Motion**: Current instant motion
- **PSI**: Current instant PSI value
- **Cooldown**: 3 seconds between distress alerts

### 5. BLE Proximity Beacon

**Configuration:**
- **Device Name**: `ESP32-StressBall`
- **TX Power**: +9 dBm (maximum range)
- **Advertising Interval**: 20-40ms (fast detection)
- **Coexistence**: WiFi/BLE balanced mode with power saving disabled
- **Health Check**: Automatic restart every 30 seconds

**Reliability Features:**
- Proper BT stack initialization (`btStart()`)
- WiFi power saving disabled for consistent radio access
- Global advertising pointer properly assigned
- Automatic recovery if advertising stops

**RSSI-Based Proximity (Raspberry Pi scanner):**
- **NEAR**: RSSI > -68 dBm (~0-2 meters)
- **MEDIUM**: RSSI -68 to -82 dBm (~2-5 meters)
- **FAR**: RSSI -82 to -92 dBm (~5-10 meters)
- **OUT_OF_RANGE**: RSSI < -92 dBm (>10 meters)

### 6. WiFi AP Mode + UDP Communication

**WiFi Access Point:**
- **SSID**: `ESP32_StressBall`
- **Password**: `12345678`
- **Mode**: AP (Access Point)
- **IP**: Auto-assigned by ESP32

**UDP Communication:**
- **ESP32 → Pi**: Port 4210 (sensor data)
- **Pi → ESP32**: Port 5006 (commands)
- **Heartbeat**: Every 5 seconds (keeps Pi informed)

**UDP Message Format (ESP32 → Pi):**
```
device:ESP32-BALL,time:12345,fsr1_raw:2048,fsr2_raw:1856,psi1:6.54,psi2:5.32,psi_max:6.54,grip_state:Stressed,ax:1024,ay:-512,az:16384,gx:128,gy:-64,gz:32,motion:Tremble,action:Squeeze,alert:PATTERN_3GRIP,dominant_type:Stressed
```

**Supported Commands (Pi → ESP32):**
| Command | Format | Description |
|---------|--------|-------------|
| Play | `play:5` | Play track 5 from SD card |
| Stop | `stop` | Stop current playback |
| Volume | `volume:25` | Set volume (0-30) |
| Music Choice | `music:3` | Set default track for alerts |
| Find Device | `play:14` | Track 14 @ max volume (5s) |

### 7. Audio System (DFPlayer Mini)

**Features:**
- MP3 files: `001.mp3`, `002.mp3`, ... on SD card (FAT32)
- Volume range: 0-30
- Default volume: 30

**Special Behavior - Track 14 (Find My Device):**
1. Receives `play:14` command from Pi
2. Sets volume to **30 (max)** immediately
3. Plays track for **5 seconds**
4. Restores to previously configured volume

**Audio Triggers:**
- Only plays on pattern completion (5-grip or 5-motion)
- Plays track number set by `music:X` command from Pi
- Cooldown: 3 seconds between audio plays

## Communication Flow

```
┌─────────────┐                    ┌──────────────┐
│   ESP32     │◄────BLE RSSI──────►│ Raspberry Pi │
│ Stress Ball │                    │   Scanner    │
└─────────────┘                    └──────────────┘
       │                                   │
       │        UDP Port 4210              │
       ├──── Sensor Data (every 5s) ──────►│
       │        or on distress             │
       │                                   │
       │        UDP Port 5006              │
       │◄──── Commands (play/stop/vol) ────┤
       │                                   │
```

## Technical Specifications

### Processing Performance
- **Loop Cycle**: ~50Hz (20ms base delay + 5ms FSR sampling)
- **FSR Sampling**: 5 samples @ 0.5ms = 5ms per sensor
- **Motion Sampling**: 6-axis read via I2C (~2ms)
- **BLE Health Check**: Every 30 seconds

### Memory Usage
- **Motion History**: 50 samples (non-None motions only)
- **PSI History**: 250 samples (5 seconds @ 50Hz)
- **Pattern Buffers**: 5 grip states + sequence tracking

### Power Consumption
- **Normal Operation**: ~150-200mA (WiFi + BLE active)
- **Peak**: ~250mA (during audio playback)
- **Power Saving**: Disabled for BLE reliability (USB powered)

## Firmware Dependencies

```ini
lib_deps =
    DFRobotDFPlayerMini @ 1.0.6
    Adafruit MPU6050 @ 2.2.6
    MPU6050 @ 1.4.4
    ESP32 BLE Arduino @ 2.0.0
    WiFi @ 2.0.0
    Wire @ 2.0.0
```

## Calibration Guide

### FSR Pressure Calibration
1. Measure actual grip force with scale
2. Record ADC values at known forces
3. Adjust PSI thresholds if needed
4. Test with target user (child's grip strength varies)

### Motion Threshold Calibration
1. Enable `DEBUG_MOTION = true`
2. Perform each motion type deliberately
3. Record accelerometer/gyro values
4. Adjust thresholds if too sensitive/insensitive

### BLE RSSI Calibration
1. Measure RSSI at exactly 1 meter distance
2. Update `BLE_TX_POWER` constant (typically -59 to -65)
3. Test proximity zones with Pi scanner
4. Adjust Pi thresholds if needed

## Known Behaviors

### By Design
- **Silent on single grips**: Only alerts on 5-grip patterns
- **Motion history ignores "None"**: Prevents "no motion" from drowning out real motions
- **PSI aggregation**: Periodic updates show average, not instant values
- **BLE restarts every 30s**: Ensures beacon stays active

### Troubleshooting
- **ESP32 reboots**: Check serial monitor for watchdog resets (should be fixed with BLE coexistence)
- **Pi can't detect beacon**: Verify BLE advertising started (check serial: `[BLE] Beacon started`)
- **No UDP data on Pi**: ESP32 sends every 5s - check WiFi connection
- **Audio not playing**: Check SD card (FAT32), file names (001.mp3), wiring (1kΩ resistor on TX)

## System Initialization Sequence

1. **Serial Init** (115200 baud)
2. **ADC Setup** (11dB attenuation for 0-3.3V range)
3. **I2C Init** (MPU6050 @ 400kHz)
4. **DFPlayer Init** (9600 baud, 1s delay for SD detection)
5. **BLE Setup** (coexistence mode + advertising start)
6. **WiFi AP Start** (SSID broadcast + UDP listener on port 5006)
7. **Ready** (loop begins at ~50Hz)

## Version Information

- **Platform**: ESP32 (Espressif 32 @ 6.12.0)
- **Framework**: Arduino (framework-arduinoespressif32 @ 3.20017.241212)
- **Build Mode**: Release
- **Last Updated**: 2026-01-16

---

**Device MAC Address**: EC:E3:34:D7:48:EA (for BLE scanner configuration)

