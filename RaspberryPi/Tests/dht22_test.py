#!/usr/bin/env python3

import time
import board
import adafruit_dht

# ======================
# DHT22 SETUP
# ======================
DHT_PIN = board.D4  # GPIO4 (Pin 7)

print("===================================")
print(" DHT22 Availability Test (GPIO4) ")
print("===================================")

try:
    dht = adafruit_dht.DHT22(DHT_PIN, use_pulseio=False)
    print("[INFO] DHT22 object created successfully")
except Exception as e:
    print("[ERROR] Failed to initialize DHT22:", e)
    exit(1)

print("[INFO] Reading sensor data... (Ctrl+C to stop)\n")

while True:
    try:
        temperature = dht.temperature
        humidity = dht.humidity

        if temperature is not None and humidity is not None:
            print(
                f"Temperature: {temperature:.1f}°C | "
                f"Humidity: {humidity:.1f}%"
            )
        else:
            print("[WARN] Sensor returned None values")

    except RuntimeError as error:
        # Expected occasional read errors
        print("[WARN] Reading error:", error)

    except Exception as error:
        print("[FATAL] Unexpected error:", error)
        break

    time.sleep(2)
