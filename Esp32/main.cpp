#include <WiFi.h>
#include <WiFiUdp.h>
#include <HardwareSerial.h>
#include <DFRobotDFPlayerMini.h>
#include <Wire.h>
#include <MPU6050.h>
#include <math.h>
#include <BLEDevice.h>
#include <BLEUtils.h>
#include <BLEAdvertising.h>
#include <esp_coexist.h>
#include <esp_wifi.h>

// ===================== CONFIG =====================
const char* AP_SSID = "ESP32_StressBall";
const char* AP_PASS = "12345678";

const char* PI_IP = "192.168.4.2";  // Pi AP mode IP
const uint16_t PI_PORT = 4210;      // Pi receives sensor data
const uint16_t ESP_COMMAND_PORT = 5006; // ESP receives Pi commands

// ===================== BLE BEACON CONFIG =====================
// ESP32 advertises as BLE beacon, Raspberry Pi scans and measures RSSI
const char* BLE_DEVICE_NAME = "ESP32-StressBall";
// TX Power at 1 meter (calibrate this for accuracy)
// Measure RSSI at exactly 1 meter and use that value
const int8_t BLE_TX_POWER = -59;  // Typical value, adjust after calibration

BLEAdvertising *pAdvertising;

// Pins
const int FSR1_PIN = 34;
const int FSR2_PIN = 35;
const int FSR_THRESHOLD = 1000;  // Legacy threshold (kept for compatibility)

// ===================== FSR TO PSI CONFIGURATION =====================
// Circuit: FSR in voltage divider with 10kΩ resistor
// 10kΩ Resistor Color Code: Brown-Black-Orange-Gold
const float VCC = 3.3;                    // ESP32 ADC reference voltage
const float ADC_MAX = 4095.0;             // 12-bit ADC resolution
const float R_FIXED = 10000.0;            // 10kΩ fixed resistor
const float FSR_AREA_MM2 = 20.0;          // FSR active area in mm² (typical for FSR402)
const int FSR_SAMPLES = 5;                // Number of samples for averaging (reduced for BLE performance)

// ===================== CHILD GRIP THRESHOLDS (PSI) =====================
// Calibrated for autism child tantrum detection
// Children aged 3-12 have lower grip strength than adults
// These thresholds detect escalating emotional states

const float PSI_NO_GRIP = 0.1;            // Below this = no contact
const float PSI_CALM = 0.5;               // Light hold - child is calm
const float PSI_MODERATE = 4.0;           // Moderate grip - mild anxiety/restlessness
const float PSI_STRESSED = 8.0;           // Firm grip - stressed/agitated state
const float PSI_TANTRUM = 16.0;            // Hard grip - tantrum/meltdown detected

// Grip state enumeration
enum GripState {
  GRIP_NONE,        // No contact with ball
  GRIP_CALM,        // Relaxed holding - baseline state
  GRIP_MODERATE,    // Slight anxiety - early warning
  GRIP_STRESSED,    // Elevated stress - intervention may help
  GRIP_TANTRUM      // Tantrum/meltdown - immediate attention needed
};

// Consecutive readings required to confirm state change (prevents false triggers)
const int GRIP_STATE_CONFIRM_COUNT = 5;

// ===================== DEBUG MODE =====================
// Set to true to see real-time sensor values for calibration
bool DEBUG_MOTION = true;           // Enable motion debug output
bool DEBUG_MOTION_VERBOSE = false;  // Show all values every loop (very spammy)
unsigned long lastMotionDebugTime = 0;
const unsigned long MOTION_DEBUG_INTERVAL = 500;  // Print debug every 500ms

// DFPlayer pins
#define PIN_MP3_TX 26
#define PIN_MP3_RX 27
int currentVolume = 30;
bool alarmPlaying = false;
unsigned long alarmStartTime = 0;
const unsigned long ALARM_DURATION = 5000;  // 5 seconds for alarm

// MPU pins
#define I2C_SDA 21
#define I2C_SCL 22

// Cooldown
const unsigned long COOLDOWN_MS = 1000;

// ===================== OBJECTS =====================
HardwareSerial mp3Serial(1);
DFRobotDFPlayerMini dfplayer;
MPU6050 mpu;
WiFiUDP udp;

// ===================== STATE =====================
unsigned long lastTriggerTime = 0;
unsigned long lastUDPSend = 0;
int musicChoice = 1;
bool isPlaying = false;

// Consecutive motion tracking
String lastMotionType = "";
int consecutiveMotionCount = 0;
const int CONSECUTIVE_MOTION_THRESHOLD = 5;

// Motion aggregation for periodic updates (track most frequent motion in 5s window)
const int MAX_MOTION_HISTORY = 50;  // Store up to 50 motion detections per 5s period
String motionHistory[MAX_MOTION_HISTORY];
int motionHistoryCount = 0;

// PSI aggregation for periodic updates (track average PSI over 5s window)
const int MAX_PSI_HISTORY = 250;  // Store up to 250 samples (5s at 20ms loop = ~250 samples)
float psiHistory[MAX_PSI_HISTORY];
int psiHistoryCount = 0;

// Grip state tracking
GripState currentGripState = GRIP_NONE;
GripState lastDetectedGripState = GRIP_NONE;
int gripStateConfirmCounter = 0;
float lastPSI1 = 0.0;
float lastPSI2 = 0.0;

// ===================== PATTERN DETECTION STATE =====================
const unsigned long GAP_MAX_MS = 1000;      // Max gap allowed between grips (1000ms)
const int GRIP_PATTERN_COUNT = 5;           // Number of grips to trigger
int sequenceCount = 0;                      // Current grip number (0-based or 1-based tracking)
unsigned long lastReleaseTime = 0;          // Time when last grip was released
bool isGripping = false;                    // Are we currently in a grip?
GripState currentMaxGrip = GRIP_NONE;       // Max grip level reached during current grip
GripState sequenceGrips[5];                 // Store grip types for the pattern
GripState dominantGripType = GRIP_STRESSED; // The dominant type across all 5 grips


// ===================== BLE BEACON SETUP =====================
// Simple BLE beacon for Pi proximity detection
// The ESP32 MAC address is: EC:E3:34:D7:48:EA (use this in Pi scanner)

void setupBLE() {
  Serial.println("[BLE] Initializing BLE beacon...");

  // Enable BT stack and configure WiFi/BLE coexistence
  // ESP32 shares 2.4GHz radio between WiFi and BLE - must configure coexistence
  btStart();

  // Set coexistence preference (use BT constant for better BLE performance)
  #ifdef ESP_COEX_PREFER_BT
    esp_coex_preference_set(ESP_COEX_PREFER_BT);
    Serial.println("[BLE] Coexistence mode: PREFER_BT");
  #else
    // Fallback: Disable WiFi power saving for better BLE reliability
    esp_wifi_set_ps(WIFI_PS_NONE);
    Serial.println("[BLE] WiFi power saving disabled for BLE reliability");
  #endif

  // Initialize BLE with device name
  BLEDevice::init("ESP32-StressBall");

  // Set TX power to maximum for better range
  esp_ble_tx_power_set(ESP_BLE_PWR_TYPE_DEFAULT, ESP_PWR_LVL_P9);
  esp_ble_tx_power_set(ESP_BLE_PWR_TYPE_ADV, ESP_PWR_LVL_P9);

  // Get advertising handle and assign to global variable
  pAdvertising = BLEDevice::getAdvertising();

  // Configure advertisement data
  BLEAdvertisementData advData;
  advData.setFlags(ESP_BLE_ADV_FLAG_GEN_DISC | ESP_BLE_ADV_FLAG_BREDR_NOT_SPT);
  advData.setName("ESP32-StressBall");

  pAdvertising->setAdvertisementData(advData);

  // Set fast advertising interval for better detection
  pAdvertising->setMinInterval(0x20);   // 20ms
  pAdvertising->setMaxInterval(0x40);   // 40ms

  // Start advertising
  pAdvertising->start();

  Serial.println("[BLE] Beacon started: ESP32-StressBall");
  Serial.println("[BLE] TX Power: MAX (+9 dBm), Interval: 20-40ms");
}

// ===================== HELPERS =====================
long getMagnitude(int16_t ax, int16_t ay, int16_t az) {
  long la = ax, lb = ay, lc = az;
  return sqrt((double)(la*la + lb*lb + lc*lc));
}

// ===================== FSR TO PSI CONVERSION =====================
// Converts raw ADC reading to PSI (pounds per square inch)
// Uses voltage divider formula and FSR characteristic curve

float adcToPSI(int adcValue) {
  // Prevent division by zero and filter noise
  if (adcValue < 50) return 0.0;

  // Step 1: Calculate voltage from ADC reading
  float voltage = adcValue * (VCC / ADC_MAX);

  // Step 2: Calculate FSR resistance using voltage divider formula
  // Vout = Vcc * R_fixed / (R_fixed + R_fsr)
  // Solving for R_fsr: R_fsr = R_fixed * (Vcc - Vout) / Vout
  float fsrResistance = R_FIXED * (VCC - voltage) / voltage;

  // Step 3: Convert resistance to force (Newtons)
  // Based on FSR 402 characteristic curve: R ≈ 1/F^1.1 (approximately)
  // Force (N) ≈ (1,000,000 / R)^(1/1.1)
  float forceN = 0.0;
  if (fsrResistance > 0 && fsrResistance < 1000000) {
    forceN = pow(1000000.0 / fsrResistance, 0.909);  // 1/1.1 ≈ 0.909
  }

  // Step 4: Convert force to PSI
  // PSI = Force(N) / Area(m²) / 6894.76 (Pa per PSI)
  // Area in m² = Area_mm² * 1e-6
  float areaM2 = FSR_AREA_MM2 * 1e-6;
  float psi = forceN / (areaM2 * 6894.76);

  // Clamp to reasonable range for child grip (0-30 PSI max)
  if (psi > 30.0) psi = 30.0;

  return psi;
}

// Get averaged PSI reading for reliability (reduces noise)
float getAveragedPSI(int pin) {
  float total = 0.0;
  for (int i = 0; i < FSR_SAMPLES; i++) {
    total += adcToPSI(analogRead(pin));
    delayMicroseconds(500);  // 0.5ms delay (reduced from 2ms for BLE performance)
  }
  return total / FSR_SAMPLES;
}

// ===================== GRIP STATE DETECTION =====================
// Determines child's emotional state based on grip pressure

GripState detectGripState(float psi) {
  if (psi < PSI_NO_GRIP) {
    return GRIP_NONE;
  } else if (psi < PSI_CALM) {
    return GRIP_CALM;
  } else if (psi < PSI_MODERATE) {
    return GRIP_MODERATE;
  } else if (psi < PSI_STRESSED) {
    return GRIP_STRESSED;
  } else {
    return GRIP_TANTRUM;
  }
}

// Convert grip state to readable string
String gripStateToString(GripState state) {
  switch (state) {
    case GRIP_NONE:     return "None";
    case GRIP_CALM:     return "Calm";
    case GRIP_MODERATE: return "Moderate";
    case GRIP_STRESSED: return "Stressed";
    case GRIP_TANTRUM:  return "Tantrum";
    default:            return "Unknown";
  }
}

// Update grip state with confirmation (prevents false triggers)
// Returns true if state changed and was confirmed
bool updateGripState(float psi1, float psi2) {
  // Use the higher PSI reading (dominant hand or stronger grip)
  float maxPSI = max(psi1, psi2);

  GripState detected = detectGripState(maxPSI);

  if (detected == lastDetectedGripState) {
    gripStateConfirmCounter++;
  } else {
    gripStateConfirmCounter = 1;
    lastDetectedGripState = detected;
  }

  // Confirm state change after consistent readings
  if (gripStateConfirmCounter >= GRIP_STATE_CONFIRM_COUNT) {
    if (detected != currentGripState) {
      GripState previousState = currentGripState;
      currentGripState = detected;

      Serial.print("[GRIP] State changed: ");
      Serial.print(gripStateToString(previousState));
      Serial.print(" -> ");
      Serial.println(gripStateToString(currentGripState));

      return true;  // State changed
    }
  }

  return false;  // No change
}

// Check if child is in distress (tantrum or stressed state)
bool isChildInDistress() {
  return (currentGripState == GRIP_TANTRUM || currentGripState == GRIP_STRESSED);
}

// Determine dominant grip type from the 3-grip sequence
// Returns GRIP_TANTRUM if 2+ tantrum grips, otherwise GRIP_STRESSED
GripState getDominantGripType() {
  int tantrumCount = 0;
  int stressedCount = 0;

  for (int i = 0; i < GRIP_PATTERN_COUNT; i++) {
    if (sequenceGrips[i] == GRIP_TANTRUM) {
      tantrumCount++;
    } else if (sequenceGrips[i] == GRIP_STRESSED) {
      stressedCount++;
    }
  }

  // Tantrum is dominant if 2 or more tantrum grips
  if (tantrumCount >= 2) {
    return GRIP_TANTRUM;
  }
  return GRIP_STRESSED;
}

// Get most frequent motion from history (excludes "None" unless it's the only motion)
String getMostFrequentMotion() {
  if (motionHistoryCount == 0) {
    return "None";
  }

  // Count frequency of each motion type
  struct MotionCount {
    String type;
    int count;
  };

  MotionCount counts[10];  // Max 10 different motion types
  int uniqueCount = 0;

  for (int i = 0; i < motionHistoryCount; i++) {
    String motion = motionHistory[i];

    // Find if this motion type already counted
    bool found = false;
    for (int j = 0; j < uniqueCount; j++) {
      if (counts[j].type == motion) {
        counts[j].count++;
        found = true;
        break;
      }
    }

    // New motion type
    if (!found && uniqueCount < 10) {
      counts[uniqueCount].type = motion;
      counts[uniqueCount].count = 1;
      uniqueCount++;
    }
  }

  // Find most frequent (excluding "None" if other motions exist)
  String mostFrequent = "None";
  int maxCount = 0;
  bool hasNonNone = false;

  for (int i = 0; i < uniqueCount; i++) {
    if (counts[i].type != "None") {
      hasNonNone = true;
      if (counts[i].count > maxCount) {
        maxCount = counts[i].count;
        mostFrequent = counts[i].type;
      }
    }
  }

  // If only "None" motions, return "None"
  if (!hasNonNone) {
    return "None";
  }

  return mostFrequent;
}

// Get average PSI from history (for periodic updates)
float getAveragePSI() {
  if (psiHistoryCount == 0) {
    return 0.0;
  }

  float total = 0.0;
  for (int i = 0; i < psiHistoryCount; i++) {
    total += psiHistory[i];
  }

  return total / psiHistoryCount;
}

// ===================== MOTION DETECTION =====================
// Thresholds increased for ball toy - needs significant motion to trigger
bool detectSpinning(int16_t gx, int16_t gy, int16_t gz) {
  const int spinThreshold = 25000;  // Was 10000 - now needs strong spin
  static unsigned long spinStartTime = 0;

  if (abs(gz) > spinThreshold) {
    if (spinStartTime == 0) spinStartTime = millis();
    if (millis() - spinStartTime > 500) {
      spinStartTime = 0;
      return true;
    }
  } else spinStartTime = 0;

  return false;
}

bool detectRocking(int16_t ax, int16_t ay) {
  static unsigned long lastCrossTime = 0;
  static int crossCount = 0;
  static bool wasPositive = true;

  const int tiltThreshold = 12000;  // Was 5000 - now needs bigger tilt
  unsigned long now = millis();

  bool isPositive = (ax > tiltThreshold);
  bool isNegative = (ax < -tiltThreshold);

  if (now - lastCrossTime > 1500) crossCount = 0;

  if ((wasPositive && isNegative) || (!wasPositive && isPositive)) {
    crossCount++;
    lastCrossTime = now;
    wasPositive = isPositive;
  }

  if (crossCount >= 4) {
    crossCount = 0;
    return true;
  }

  return false;
}

bool detectBouncing(int16_t az) {
  static int bounceCount = 0;
  static unsigned long lastBounceTime = 0;

  const int impactThreshold = 28000;  // Was 20000 - now needs harder bounce
  unsigned long now = millis();

  if (now - lastBounceTime > 1000) bounceCount = 0;

  if (az > impactThreshold) {
    if (now - lastBounceTime > 200) {
      bounceCount++;
      lastBounceTime = now;
    }
  }

  if (bounceCount >= 3) {
    bounceCount = 0;
    return true;
  }
  return false;
}

bool detectFreeFall(int16_t ax, int16_t ay, int16_t az) {
  long mag = getMagnitude(ax, ay, az);
  static unsigned long fallStartTime = 0;

  const int freeFallThreshold = 1500;   // Was 2000 - stricter (must be closer to zero-g)
  const int minFallDuration = 150;      // Was 100 - needs longer fall time

  if (mag < freeFallThreshold) {
    if (fallStartTime == 0) fallStartTime = millis();
    else if (millis() - fallStartTime > minFallDuration) return true;
  } else fallStartTime = 0;

  return false;
}

bool detectImpact(int16_t ax, int16_t ay, int16_t az) {
  return getMagnitude(ax, ay, az) > 38000;  // Was 30000 - now needs harder impact
}

bool detectViolentShake(int16_t ax, int16_t ay, int16_t az) {
  static long lastMag = 0;
  static int shakeCount = 0;
  static unsigned long lastTime = 0;

  long mag = getMagnitude(ax, ay, az);
  long delta = abs(mag - lastMag);

  const int shakeThreshold = 15000;   // Was 8000 - now needs violent shaking
  const int countThreshold = 12;      // Was 10 - needs more shakes

  if (millis() - lastTime > 1000) shakeCount = 0;

  if (delta > shakeThreshold) {
    shakeCount++;
    lastTime = millis();
  }

  lastMag = mag;

  if (shakeCount >= countThreshold) {
    shakeCount = 0;
    return true;
  }

  return false;
}

bool detectTremble(int16_t ax, int16_t ay, int16_t az) {
  static long lastMag = 0;
  static int trembleCount = 0;
  static unsigned long lastTime = 0;
  static unsigned long lastCountTime = 0;

  long mag = getMagnitude(ax, ay, az);
  long delta = abs(mag - lastMag);

  // Thresholds raised for ball toy - needs real trembling, not just movement
  const int trembleThreshold = 6000;  // Was 3500 - minimum change to count as tremble
  const int trembleMax = 14000;       // Was 7000 - max change (above = shake)
  const int required = 18;            // Was 15 - needs more trembles
  const int windowMs = 800;           // Time window to accumulate trembles
  const int minTimeBetweenCounts = 30; // Minimum ms between counting trembles

  // Reset if window expired
  if (millis() - lastTime > windowMs) trembleCount = 0;

  // Only count if enough time passed since last count (prevents rapid false counting)
  if (delta > trembleThreshold && delta < trembleMax) {
    if (millis() - lastCountTime > minTimeBetweenCounts) {
      trembleCount++;
      lastCountTime = millis();
      lastTime = millis();
    }
  }

  lastMag = mag;

  if (trembleCount >= required) {
    trembleCount = 0;
    return true;
  }

  return false;
}

// ===================== MOTION DEBUG =====================
// Prints real-time sensor values to help calibrate thresholds
// void printMotionDebug(int16_t ax, int16_t ay, int16_t az, int16_t gx, int16_t gy, int16_t gz) {
//   if (!DEBUG_MOTION) return;
//   if (millis() - lastMotionDebugTime < MOTION_DEBUG_INTERVAL) return;
//   lastMotionDebugTime = millis();

//   long mag = getMagnitude(ax, ay, az);
//   static long lastMag = 0;
//   long delta = abs(mag - lastMag);
//   lastMag = mag;

  // Serial.println("========== MOTION DEBUG ==========");
  // Serial.print("Accel: X=");
  // Serial.print(ax);
  // Serial.print(" Y=");
  // Serial.print(ay);
  // Serial.print(" Z=");
  // Serial.println(az);

  // Serial.print("Gyro:  X=");
  // Serial.print(gx);
  // Serial.print(" Y=");
  // Serial.print(gy);
  // Serial.print(" Z=");
  // Serial.println(gz);

  // Serial.print("Magnitude: ");
  // Serial.print(mag);
  // Serial.print(" | Delta: ");
  // Serial.println(delta);

  // Serial.println("--- Thresholds Reference ---");
  // Serial.println("Impact:    mag > 30000");
  // Serial.println("Bounce:    az > 20000 (3x in 1s)");
  // Serial.println("FreeFall:  mag < 2000 for 100ms");
  // Serial.println("Shake:     delta > 8000 (10x in 1s)");
  // Serial.println("Spin:      gz > 10000 for 500ms");
  // Serial.println("Rock:      ax crosses 5000 (4x in 1.5s)");
  // Serial.println("Tremble:   delta 3500-7000 (15x in 800ms)");
  // Serial.println("==================================");
// }

// ===================== PLAY SOUND =====================
void playSound(int idx) {
  dfplayer.stop();
  delay(80);

  dfplayer.play(idx);
  delay(50);                 // DFPlayer needs time to latch track
  dfplayer.volume(currentVolume);

  isPlaying = true;

  Serial.print("[AUDIO] Playing track ");
  Serial.print(idx);
  Serial.print(" at volume ");
  Serial.println(currentVolume);
}

// ===================== SAFE UDP SEND =====================
void sendUDP(const String &msg) {
  if (millis() - lastUDPSend < 200) return;  // prevent mbox crash
  lastUDPSend = millis();

  udp.beginPacket(PI_IP, PI_PORT);
  udp.write((uint8_t*)msg.c_str(), msg.length());
  udp.endPacket();

  delay(5);  // allow network task to flush
}

// ===================== RECEIVE COMMANDS FROM PI =====================
void handlePiCommand(String cmd) {
  cmd.trim();
  cmd.toUpperCase();
  Serial.print("Handling Pi command: ");
  Serial.println(cmd);

  if (cmd == "PLAY:STOP") {
    dfplayer.stop();
    isPlaying = false;
    alarmPlaying = false;  // Clear alarm flag if stopped
  }
  else if (cmd.startsWith("PLAY:")) {
    int track = cmd.substring(5).toInt();
    dfplayer.stop();          // HARD stop current audio
    delay(80);                // Allow DFPlayer to flush buffer

    // Track 14 is "Find My Device" alarm - play at MAX volume
    if (track == 14) {
      Serial.println("[ALARM] Find My Device activated - MAX VOLUME");
      dfplayer.volume(30);    // Set to max volume
      delay(50);
      dfplayer.play(track);
      alarmPlaying = true;
      alarmStartTime = millis();
      Serial.print("[ALARM] Will restore volume to ");
      Serial.print(currentVolume);
      Serial.print(" after ");
      Serial.print(ALARM_DURATION / 1000);
      Serial.println(" seconds");
    } else {
      // Normal track - use configured volume
      dfplayer.play(track);
      dfplayer.volume(currentVolume);
    }

    isPlaying = true;
    Serial.print("[AUDIO] Switched to track ");
    Serial.println(track);
  }
  else if (cmd.startsWith("VOLUME:")) {
    int vol = cmd.substring(7).toInt();
    currentVolume = constrain(vol, 0, 30);

    dfplayer.volume(currentVolume);

    Serial.print("[AUDIO] Volume set to ");
    Serial.println(currentVolume);
  }
  // Debug mode commands
  else if (cmd == "DEBUG:ON") {
    DEBUG_MOTION = true;
    Serial.println("[DEBUG] Motion debug ENABLED");
  }
  else if (cmd == "DEBUG:OFF") {
    DEBUG_MOTION = false;
    Serial.println("[DEBUG] Motion debug DISABLED");
  }
  else if (cmd == "DEBUG:VERBOSE") {
    DEBUG_MOTION_VERBOSE = !DEBUG_MOTION_VERBOSE;
    Serial.print("[DEBUG] Verbose mode: ");
    Serial.println(DEBUG_MOTION_VERBOSE ? "ON" : "OFF");
  }
  else if (cmd == "STATUS") {
    // Send back current status
    String status = "STATUS:debug=" + String(DEBUG_MOTION ? "on" : "off");
    status += ",grip=" + gripStateToString(currentGripState);
    status += ",psi=" + String(max(lastPSI1, lastPSI2), 2);
    status += ",ble=stealth";
    Serial.println(status);
    sendUDP(status);
  }
  else {
    Serial.println("Unknown command. Available: PLAY:n, PLAY:STOP, VOLUME:n, DEBUG:ON, DEBUG:OFF, DEBUG:VERBOSE, STATUS");
  }
}

// ===================== SETUP =====================
void setup() {
  Serial.begin(115200);
  delay(300);

  Serial.println("========================================");
  Serial.println("   ESP32 Stress Ball  ");
  Serial.println("========================================");

  analogSetPinAttenuation(FSR1_PIN, ADC_11db);
  analogSetPinAttenuation(FSR2_PIN, ADC_11db);

  Wire.begin(I2C_SDA, I2C_SCL);
  mpu.initialize();
  Serial.println("[MPU6050] Initialized");

  mp3Serial.begin(9600, SERIAL_8N1, PIN_MP3_RX, PIN_MP3_TX);
  delay(500);

  Serial.println("[DEBUG] Initializing DFPlayer...");
  if (!dfplayer.begin(mp3Serial)) {
    Serial.println("[ERROR] DFPlayer init FAILED! Check:");
    Serial.println("  - SD card inserted and FAT32 formatted?");
    Serial.println("  - MP3 files named 001.mp3, 002.mp3, etc?");
    Serial.println("  - TX/RX wiring correct? (ESP TX->DFPlayer RX)");
    Serial.println("  - 1K resistor on TX line?");
  } else {
    Serial.println("[DEBUG] DFPlayer initialized successfully!");
  }

  delay(1000);
  dfplayer.volume(30);
  Serial.println("[DEBUG] Volume set to 30");

  // Initialize BLE Beacon
  setupBLE();

  // WiFi AP
  WiFi.mode(WIFI_AP);
  WiFi.softAP(AP_SSID, AP_PASS);
  delay(400);

  udp.begin(ESP_COMMAND_PORT);
  Serial.println("[WiFi] AP started: " + String(AP_SSID));
  Serial.println("[WiFi] UDP command listener on port " + String(ESP_COMMAND_PORT));

  // Test DFPlayer at startup
  Serial.println("[DEBUG] Testing DFPlayer");
  dfplayer.volume(0);      // mute
  delay(200);
  dfplayer.stop();         // ensure idle
  delay(200);
  dfplayer.volume(30);     // restore default volume
  Serial.println("[DEBUG] Startup test complete. Ready for sensor input.");

  Serial.println("========================================");
  Serial.println("   System Ready - Monitoring Active");
  Serial.println("========================================");
}

// ===================== MAIN LOOP =====================
void loop() {
  // ----- 1) RECEIVE COMMANDS -----
  int packetSize = udp.parsePacket();
  if (packetSize) {
    char buffer[256];
    int len = udp.read(buffer, sizeof(buffer) - 1);
    if (len > 0) buffer[len] = '\0';
    handlePiCommand(String(buffer));
  }

  // ----- 2) SENSOR READING -----
  // Read raw ADC values
  int fsr1_raw = analogRead(FSR1_PIN);
  int fsr2_raw = analogRead(FSR2_PIN);

  // Convert to PSI with averaging for reliability
  lastPSI1 = getAveragedPSI(FSR1_PIN);
  lastPSI2 = getAveragedPSI(FSR2_PIN);
  float maxPSI = max(lastPSI1, lastPSI2);

  // Record PSI to history for aggregation (for periodic updates)
  if (psiHistoryCount < MAX_PSI_HISTORY) {
    psiHistory[psiHistoryCount] = maxPSI;
    psiHistoryCount++;
  }

  // Update grip state (with confirmation to prevent false triggers)
  bool gripStateChanged = updateGripState(lastPSI1, lastPSI2);

  // Determine if child is squeezing (any significant pressure)
  bool squeeze = (maxPSI > PSI_NO_GRIP);

  // ===================== 3-GRIP PATTERN LOGIC =====================
  // Logic: 3 distinct grips > PSI_STRESSED with gap < 3s between them.
  
  bool patternTriggered = false;
  
  // 1. Detect Grip Start (Pressure > Stressed Threshold)
  if (maxPSI >= PSI_STRESSED) {
    if (!isGripping) {
      // START of a new grip
      isGripping = true;
      currentMaxGrip = detectGripState(maxPSI); // Initialize max for this grip
      
      unsigned long timeSinceLastRelease = millis() - lastReleaseTime;
      
      // Check Gap Logic
      if (sequenceCount > 0) {
        // We have previous grips. Check if gap is valid.
        if (timeSinceLastRelease > GAP_MAX_MS) {
           // TIMEOUT: Gap too long. Reset sequence.
           Serial.println("[PATTERN] Gap too long (" + String(timeSinceLastRelease) + "ms). Resetting sequence.");
           sequenceCount = 0; 
           // Treat this as the NEW first grip
        } else {
           // VALID GAP: Continue sequence
           Serial.println("[PATTERN] Valid gap (" + String(timeSinceLastRelease) + "ms). Grip #" + String(sequenceCount + 1));
        }
      }
      
      // Increment count for this new grip
      sequenceCount++;
      
      // CHECK COMPLETION (Trigger on Start of 3rd Grip)
      if (sequenceCount >= GRIP_PATTERN_COUNT) {
        patternTriggered = true;

        // Store the 3rd grip type
        sequenceGrips[GRIP_PATTERN_COUNT - 1] = currentMaxGrip;

        // Determine dominant grip type across all 3 grips
        dominantGripType = getDominantGripType();

        Serial.println("[PATTERN] 3-GRIP PATTERN DETECTED!");
        Serial.print("[PATTERN] Grips: ");
        Serial.print(gripStateToString(sequenceGrips[0]));
        Serial.print(" -> ");
        Serial.print(gripStateToString(sequenceGrips[1]));
        Serial.print(" -> ");
        Serial.println(gripStateToString(sequenceGrips[2]));
        Serial.print("[PATTERN] Dominant type: ");
        Serial.println(gripStateToString(dominantGripType));

        // Reset sequence (keep isGripping=true to avoid double counting)
        sequenceCount = 0;
      }
    } else {
      // CONTINUING a grip
      // Update max grip strength observed during this hold
      GripState potentialState = detectGripState(maxPSI);
      if (potentialState > currentMaxGrip) {
        currentMaxGrip = potentialState;
      }
    }
  } else {
    // RELEASE (Pressure < Stressed Threshold)
    if (isGripping) {
      // END of a grip
      isGripping = false;
      lastReleaseTime = millis();
      Serial.println("[PATTERN] Grip released. Waiting for next...");
      
      // Store the max grip we saw (if we haven't triggered/reset yet)
      // Note: If we triggered, sequenceCount is already 0.
      if (sequenceCount > 0 && sequenceCount < GRIP_PATTERN_COUNT) {
        sequenceGrips[sequenceCount - 1] = currentMaxGrip;
      }
    }
  }

  // Check if child is in distress state
  bool inDistress = isChildInDistress();

  int16_t ax, ay, az, gx, gy, gz;
  mpu.getMotion6(&ax, &ay, &az, &gx, &gy, &gz);

  // Print motion debug info (controlled by DEBUG_MOTION flag)
  // printMotionDebug(ax, ay, az, gx, gy, gz);

  String motion = "";
  if (detectImpact(ax, ay, az)) motion = "Impact";
  else if (detectBouncing(az)) motion = "Bounce";
  else if (detectFreeFall(ax, ay, az)) motion = "FreeFall";
  else if (detectViolentShake(ax, ay, az)) motion = "ViolentShake";
  else if (detectSpinning(gx, gy, gz)) motion = "Spinning";
  else if (detectRocking(ax, ay)) motion = "Rocking";
  else if (detectTremble(ax, ay, az)) motion = "Tremble";
  else motion = "None";

  // Record motion to history ONLY if it's not "None" (for periodic updates)
  // This way, actual motions aren't drowned out by hundreds of "None" entries
  if (motion != "None" && motionHistoryCount < MAX_MOTION_HISTORY) {
    motionHistory[motionHistoryCount] = motion;
    motionHistoryCount++;
  }

  // ----- 3) TRACK CONSECUTIVE MOTIONS -----
  bool shouldPlayForMotion = false;
  if (motion != "None") {
    if (motion == lastMotionType) {
      consecutiveMotionCount++;
      Serial.print("[DEBUG] Same motion detected: ");
      Serial.print(motion);
      Serial.print(" count: ");
      Serial.println(consecutiveMotionCount);
    } else {
      consecutiveMotionCount = 1;
      lastMotionType = motion;
      Serial.print("[DEBUG] New motion type: ");
      Serial.println(motion);
    }

    if (consecutiveMotionCount >= CONSECUTIVE_MOTION_THRESHOLD) {
      shouldPlayForMotion = true;
      consecutiveMotionCount = 0;  // Reset after triggering
      Serial.println("[DEBUG] 5 consecutive motions reached - triggering sound!");
    }
  }

  // ----- 4) SEND SENSOR EVENT -----
  unsigned long now = millis();

  // Distress signals that require IMMEDIATE send (bypass periodic interval)
  bool isDistressSignal = patternTriggered || shouldPlayForMotion;

  // Periodic heartbeat every 5 seconds (so Pi knows ESP32 is alive)
  static unsigned long lastPeriodicSend = 0;
  bool isPeriodicSend = (now - lastPeriodicSend >= 5000);

  // Send data when:
  // 1. IMMEDIATE: Distress signal detected (with cooldown to prevent spam)
  // 2. PERIODIC: Every 5 seconds for heartbeat/status update
  bool shouldSend = false;

  if (isDistressSignal && (now - lastTriggerTime > COOLDOWN_MS)) {
    // Immediate send for distress (respects cooldown)
    shouldSend = true;
    lastTriggerTime = now;
    lastPeriodicSend = now;  // Reset periodic timer too
  } else if (isPeriodicSend) {
    // Periodic send every 5 seconds
    shouldSend = true;
    lastPeriodicSend = now;
  }

  if (shouldSend) {
    // Determine which motion and PSI to send
    String motionToSend;
    float psiToSend;

    if (isDistressSignal) {
      // For immediate distress, use current values
      motionToSend = motion;
      psiToSend = maxPSI;
    } else {
      // For periodic updates, use aggregated values from last 5 seconds
      motionToSend = getMostFrequentMotion();
      psiToSend = getAveragePSI();
    }

    // Build comprehensive message with PSI and grip state
    String msg = "device:ESP32-BALL,";
    msg += "time:" + String(now) + ",";
    msg += "fsr1_raw:" + String(fsr1_raw) + ",";
    msg += "fsr2_raw:" + String(fsr2_raw) + ",";
    msg += "psi1:" + String(lastPSI1, 2) + ",";
    msg += "psi2:" + String(lastPSI2, 2) + ",";
    msg += "psi_max:" + String(psiToSend, 2) + ",";  // Use aggregated for periodic, current for distress
    msg += "grip_state:" + gripStateToString(currentGripState) + ",";
    msg += "ax:" + String(ax) + ",";
    msg += "ay:" + String(ay) + ",";
    msg += "az:" + String(az) + ",";
    msg += "gx:" + String(gx) + ",";
    msg += "gy:" + String(gy) + ",";
    msg += "gz:" + String(gz);
    // Send aggregated motion for periodic, current motion for distress
    msg += ",motion:" + motionToSend;
    if (squeeze) msg += ",action:Squeeze";
    // Distress alerts - only sent when pattern/motion threshold reached
    if (patternTriggered) msg += ",alert:PATTERN_3GRIP,dominant_type:" + gripStateToString(dominantGripType);
    if (shouldPlayForMotion) msg += ",alert:MOTION_3X,motion_type:" + lastMotionType;

    sendUDP(msg);

    if (isDistressSignal) {
      Serial.println("[UDP] IMMEDIATE distress: " + msg);
    } else {
      Serial.println("[UDP] Periodic update: " + msg);
      // Reset aggregation histories after periodic send
      motionHistoryCount = 0;
      psiHistoryCount = 0;
    }

    // Play sound ONLY on distress signals:
    // 1. 5-grip pattern (5 grips > PSI_STRESSED within 3s gaps)
    // 2. 5 consecutive same motions
    if (isDistressSignal) {
      if (patternTriggered) {
        Serial.print("[AUDIO] 5-Grip Pattern (");
        Serial.print(gripStateToString(dominantGripType));
        Serial.println(") - playing sound");
      } else {
        Serial.print("[AUDIO] 5x ");
        Serial.print(lastMotionType);
        Serial.println(" motions - playing sound");
      }
      playSound(musicChoice);
    }
  }


  // Restore volume after alarm finishes
  if (alarmPlaying && (now - alarmStartTime > ALARM_DURATION)) {
    dfplayer.volume(currentVolume);
    alarmPlaying = false;
    Serial.print("[ALARM] Alarm finished - volume restored to ");
    Serial.println(currentVolume);
  }

  // Debug output every 2 seconds
  static unsigned long lastDebugTime = 0;
  if (now - lastDebugTime > 2000) {
    lastDebugTime = now;
    // Read raw ADC for debug (separate from averaged PSI)
    Serial.print("[DEBUG] RAW1: ");
    Serial.print(fsr1_raw);
    Serial.print(" RAW2: ");
    Serial.print(fsr2_raw);
    Serial.print(" | PSI1: ");
    Serial.print(adcToPSI(fsr1_raw));
    Serial.print(" | PSI2: ");
    Serial.print(adcToPSI(fsr2_raw));
    Serial.print(" | State: ");
    Serial.println(gripStateToString(currentGripState));
  }

  // BLE health monitoring - check every 30 seconds
  static unsigned long lastBLECheck = 0;
  if (now - lastBLECheck > 30000) {
    lastBLECheck = now;

    // Check if advertising is still active
    if (pAdvertising != nullptr) {
      // Restart advertising to ensure beacon is active
      pAdvertising->stop();
      delay(50);
      pAdvertising->start();
      Serial.println("[BLE] Health check: Advertising restarted");
    } else {
      // Critical: pAdvertising is null, reinitialize BLE
      Serial.println("[BLE] WARNING: pAdvertising is NULL! Reinitializing...");
      setupBLE();
    }
  }

  delay(20);
}
