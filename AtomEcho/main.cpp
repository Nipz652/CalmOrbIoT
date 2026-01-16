#include <M5Unified.h>
#include <driver/i2s.h>

#define BAUD_RATE 921600

String commandBuffer = "";

// Tone-based voice responses
// Each beep: 500ms tone, 500ms interval between beeps
void playTonePattern(String message) {
    message.toLowerCase();

    if (message.indexOf("ready") >= 0) {
        // "I'm ready!" - 3 ascending beeps (500Hz, 1000Hz, 1500Hz)
        M5.Speaker.tone(500, 500);   // Low beep - 500ms
        delay(1000);                 // Wait 500ms tone + 500ms interval

        M5.Speaker.tone(1000, 500);  // Mid beep - 500ms
        delay(1000);                 // Wait 500ms tone + 500ms interval

        M5.Speaker.tone(1500, 500);  // High beep - 500ms
        delay(500);                  // Wait for tone to finish
        M5.Speaker.stop();
    }
    else if (message.indexOf("music") >= 0) {
        // "play music" - 2 descending beeps (1500Hz, 500Hz)
        M5.Speaker.tone(1500, 500);  // High beep - 500ms
        delay(1000);                 // Wait 500ms tone + 500ms interval

        M5.Speaker.tone(500, 500);   // Low beep - 500ms
        delay(500);                  // Wait for tone to finish
        M5.Speaker.stop();
    }
    else if (message.indexOf("animation") >= 0 || message.indexOf("anime") >= 0) {
        // "play animation" - 2 ascending beeps (500Hz, 1500Hz)
        M5.Speaker.tone(500, 500);   // Low beep - 500ms
        delay(1000);                 // Wait 500ms tone + 500ms interval

        M5.Speaker.tone(1500, 500);  // High beep - 500ms
        delay(500);                  // Wait for tone to finish
        M5.Speaker.stop();
    }
    else if (message.indexOf("both") >= 0) {
        // "play both" - 2 same volume beeps (1000Hz, 1000Hz)
        M5.Speaker.tone(1000, 500);  // Mid beep - 500ms
        delay(1000);                 // Wait 500ms tone + 500ms interval

        M5.Speaker.tone(1000, 500);  // Mid beep - 500ms
        delay(500);                  // Wait for tone to finish
        M5.Speaker.stop();
    }
    else if (message.indexOf("understand") >= 0 || message.indexOf("unknown") >= 0 || message.indexOf("sorry") >= 0 || message.indexOf("again") >= 0) {
        // "I'm sorry, try again" - 3 descending beeps (1500Hz, 1000Hz, 500Hz)
        M5.Speaker.tone(1500, 500);  // High beep - 500ms
        delay(1000);                 // Wait 500ms tone + 500ms interval

        M5.Speaker.tone(1000, 500);  // Mid beep - 500ms
        delay(1000);                 // Wait 500ms tone + 500ms interval

        M5.Speaker.tone(500, 500);   // Low beep - 500ms
        delay(500);                  // Wait for tone to finish
        M5.Speaker.stop();
    }
    else {
        // Default: Single mid beep
        M5.Speaker.tone(1000, 500);
        delay(500);
        M5.Speaker.stop();
    }
}

void handleCommand(String cmd) {
    // AVOID String class entirely - use C-style string
    const char* cmdStr = cmd.c_str();
    int patternID = 0;

    // Use strstr instead of indexOf (simpler, might not corrupt speaker)
    if (strstr(cmdStr, "ready")) patternID = 1;
    else if (strstr(cmdStr, "music")) patternID = 2;
    else if (strstr(cmdStr, "anim")) patternID = 3;
    else if (strstr(cmdStr, "both")) patternID = 4;
    else if (strstr(cmdStr, "sorry")) patternID = 5;

    // Now play based on pattern ID
    // Using tone() without duration + manual stop() for better control
    if (patternID == 1) {
        // Ready: 3 ascending
        M5.Speaker.tone(500);
        delay(500);
        M5.Speaker.stop();
        delay(500);
        M5.Speaker.tone(1000);
        delay(500);
        M5.Speaker.stop();
        delay(500);
        M5.Speaker.tone(1500);
        delay(500);
        M5.Speaker.stop();
    }
    else if (patternID == 2) {
        // Music: 2 RAPID consecutive beeps
        M5.Speaker.tone(1000);
        delay(300);
        M5.Speaker.stop();
        delay(100);  // Short 100ms gap
        M5.Speaker.tone(1000);
        delay(300);
        M5.Speaker.stop();
    }
    else if (patternID == 3) {
        // Animation: 2 RAPID consecutive beeps
        M5.Speaker.tone(1000);
        delay(300);
        M5.Speaker.stop();
        delay(100);  // Short 100ms gap
        M5.Speaker.tone(1000);
        delay(300);
        M5.Speaker.stop();
    }
    else if (patternID == 4) {
        // Both: 2 RAPID consecutive beeps
        M5.Speaker.tone(1000);
        delay(300);
        M5.Speaker.stop();
        delay(100);  // Short 100ms gap
        M5.Speaker.tone(1000);
        delay(300);
        M5.Speaker.stop();
    }
    else if (patternID == 5) {
        // Error: 2 RAPID consecutive beeps
        M5.Speaker.tone(1000);
        delay(300);
        M5.Speaker.stop();
        delay(100);  // Short 100ms gap
        M5.Speaker.tone(1000);
        delay(300);
        M5.Speaker.stop();
    }
    else {
        // Default: 1 beep
        M5.Speaker.tone(1000);
        delay(500);
        M5.Speaker.stop();
    }
}

void setup() {
    Serial.begin(BAUD_RATE);
    delay(1000);

    auto cfg = M5.config();
    cfg.led_brightness = 0;
    cfg.internal_mic = false;  // Microphone disabled
    cfg.internal_spk = true;   // Speaker enabled
    M5.begin(cfg);

    // DON'T uninstall I2S - speaker needs it!
    // i2s_driver_uninstall(I2S_NUM_0);
    // i2s_driver_uninstall(I2S_NUM_1);

    // Initialize speaker once - keep it active
    M5.Speaker.setVolume(255);
    M5.Speaker.begin();

    // Startup melody - confirms firmware loaded
    M5.Speaker.tone(1000, 200);
    delay(250);
    M5.Speaker.tone(1500, 200);
    delay(250);
    M5.Speaker.stop();

    // Keep speaker system active - don't call begin() again in loop
    // NO Serial.println() - corrupts communication
}

void loop() {
    M5.update();

    static unsigned long lastCharTime = 0;
    static bool hasData = false;

    while (Serial.available() > 0) {
        char c = Serial.read();

        // Accept any printable character OR common line endings
        if (c >= 32 && c <= 126) {
            commandBuffer += c;
            hasData = true;
            lastCharTime = millis();
        }
        else if (c == '\n' || c == '\r' || c < 32) {
            // Any control character (including corrupted newline) triggers command processing
            if (commandBuffer.length() > 0) {
                handleCommand(commandBuffer);
                commandBuffer = "";
                hasData = false;
            }
        }
    }

    // Also process command if we haven't received data for 50ms (timeout-based)
    if (hasData && (millis() - lastCharTime > 50)) {
        if (commandBuffer.length() > 0) {
            handleCommand(commandBuffer);
            commandBuffer = "";
        }
        hasData = false;
    }

    delay(1);
}
