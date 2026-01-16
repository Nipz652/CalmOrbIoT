"""
WiFi Service - Handles communication with ESP32 via WiFi dongle
"""

import json
import asyncio
import aiohttp
from config.settings import ESP32_IP, ESP32_PORT, ESP32_POLL_INTERVAL


class WiFiService:
    """Manages WiFi connection and data exchange with ESP32"""

    def __init__(self):
        self.is_connected = False
        self.esp32_data = {}
        self._on_data_received_callback = None
        self._running = False

    async def start(self):
        """Start WiFi service and begin polling ESP32"""
        print(f"[WiFi] Starting WiFi service, connecting to ESP32 at {ESP32_IP}:{ESP32_PORT}")
        self._running = True
        asyncio.create_task(self._poll_esp32())

    async def stop(self):
        """Stop WiFi service"""
        print("[WiFi] Stopping WiFi service")
        self._running = False

    async def _poll_esp32(self):
        """Continuously poll ESP32 for sensor data"""
        while self._running:
            try:
                data = await self.fetch_esp32_data()
                if data and self._on_data_received_callback:
                    self._on_data_received_callback(data)
            except Exception as e:
                print(f"[WiFi] Poll error: {e}")

            await asyncio.sleep(ESP32_POLL_INTERVAL)

    async def fetch_esp32_data(self) -> dict:
        """Fetch current data from ESP32"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"http://{ESP32_IP}:{ESP32_PORT}/data",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status == 200:
                        self.esp32_data = await response.json()
                        self.is_connected = True
                        return self.esp32_data
        except Exception as e:
            self.is_connected = False
            print(f"[WiFi] Failed to fetch ESP32 data: {e}")
        return {}

    async def send_to_esp32(self, data: dict) -> bool:
        """Send command/data to ESP32"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"http://{ESP32_IP}:{ESP32_PORT}/command",
                    json=data,
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    return response.status == 200
        except Exception as e:
            print(f"[WiFi] Failed to send to ESP32: {e}")
            return False

    def on_data_received(self, callback):
        """Register callback for when data is received from ESP32"""
        self._on_data_received_callback = callback

    def get_latest_data(self) -> dict:
        """Get the most recent ESP32 data"""
        return self.esp32_data
