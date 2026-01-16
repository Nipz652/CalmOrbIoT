"""
Sensor Service - Handles DHT22 temperature/humidity sensor
"""

import asyncio
import adafruit_dht
import board
from config.settings import DHT22_PIN, SENSOR_READ_INTERVAL


class SensorService:
    """Manages DHT22 sensor readings"""

    def __init__(self):
        self.dht_sensor = None
        self.is_running = False
        self.current_temperature = None
        self.current_humidity = None
        self._on_reading_callback = None
        self._consecutive_errors = 0
        self._max_retries = 3

    async def start(self):
        """Initialize DHT22 sensor"""
        print(f"[Sensor] Starting sensor service on GPIO {DHT22_PIN}")
        try:
            # Initialize DHT22 sensor on GPIO4
            self.dht_sensor = adafruit_dht.DHT22(board.D4)
            print("[Sensor] DHT22 sensor initialized successfully")
        except Exception as e:
            print(f"[Sensor] Failed to initialize DHT22: {e}")
        self.is_running = True
        asyncio.create_task(self._read_loop())

    async def stop(self):
        """Stop sensor service"""
        print("[Sensor] Stopping sensor service")
        self.is_running = False
        if self.dht_sensor:
            try:
                self.dht_sensor.exit()
                print("[Sensor] DHT22 sensor cleaned up")
            except Exception as e:
                print(f"[Sensor] Cleanup error: {e}")

    async def _read_loop(self):
        """Continuously read sensor data"""
        while self.is_running:
            await self.read_sensor()
            await asyncio.sleep(SENSOR_READ_INTERVAL)

    async def read_sensor(self) -> dict:
        """Read current temperature and humidity from DHT22"""
        if not self.dht_sensor:
            print("[Sensor] DHT22 sensor not initialized")
            return {}

        try:
            # Read from DHT22 sensor (may throw RuntimeError on timing issues)
            temperature = self.dht_sensor.temperature
            humidity = self.dht_sensor.humidity

            if temperature is not None and humidity is not None:
                self.current_temperature = temperature
                self.current_humidity = humidity
                self._consecutive_errors = 0
                print(f"[Sensor] Reading: {temperature:.1f}°C, {humidity:.1f}%")
            else:
                self._consecutive_errors += 1
                print(f"[Sensor] Got None values (attempt {self._consecutive_errors})")

            reading = self.get_current_reading()

            if self._on_reading_callback and self.current_temperature is not None:
                self._on_reading_callback(reading)

            return reading

        except RuntimeError as e:
            # DHT22 often throws RuntimeError on timing issues, this is normal
            self._consecutive_errors += 1
            if self._consecutive_errors <= self._max_retries:
                print(f"[Sensor] Read retry {self._consecutive_errors}/{self._max_retries}: {e}")
            else:
                print(f"[Sensor] Persistent read error: {e}")
            return self.get_current_reading()  # Return last known values

        except Exception as e:
            print(f"[Sensor] Unexpected error: {e}")
            self._consecutive_errors += 1
            return self.get_current_reading()

    def get_current_reading(self) -> dict:
        """Get the most recent sensor reading"""
        return {
            "temperature": self.current_temperature,
            "humidity": self.current_humidity,
            "unit": "celsius",
        }

    def on_reading(self, callback):
        """Register callback for sensor readings"""
        self._on_reading_callback = callback

    def get_status(self) -> dict:
        """Get sensor service status"""
        return {
            "is_running": self.is_running,
            "gpio_pin": DHT22_PIN,
            "last_reading": self.get_current_reading(),
        }
