#!/usr/bin/env python3
"""Quick script to check ESP32 connection status"""
import sys
sys.path.insert(0, '/home/abdul/fyp2')

from services.distress_service import (
    is_esp32_connected,
    is_esp32_beacon_detected,
    get_settings,
    _esp32_last_data_time,
    ESP32_CONNECTION_TIMEOUT
)
import time

print("=" * 50)
print("ESP32 Connection Status Check")
print("=" * 50)

last_data = _esp32_last_data_time
now = time.time()
time_since_last = now - last_data if last_data > 0 else -1

print(f"esp32_connected: {is_esp32_connected()}")
print(f"esp32_beacon_detected: {is_esp32_beacon_detected()}")
print(f"Last data received: {time_since_last:.1f}s ago" if time_since_last >= 0 else "Never received")
print(f"Connection timeout: {ESP32_CONNECTION_TIMEOUT}s")
print()
print("Full settings:")
settings = get_settings()
for key, value in settings.items():
    if key not in ['animations', 'sounds', 'available_animations', 'available_sounds']:
        print(f"  {key}: {value}")
