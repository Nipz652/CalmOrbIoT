"""
Pi Hub - Main Entry Point
Coordinates all services and manages data flow
"""

import asyncio
import signal
from services import (
    BLEService,
    WiFiService,
    CameraService,
    VoiceService,
    SensorService,
    DisplayService,
)
from models.data_models import PiHubData, ESP32Data, SensorReading, MobileCommand
from config.settings import BLE_SEND_INTERVAL
from utils import log_info, log_error


class PiHub:
    """Main controller that coordinates all services"""

    def __init__(self):
        # Initialize all services
        self.ble_service = BLEService()
        self.wifi_service = WiFiService()
        self.camera_service = CameraService()
        self.voice_service = VoiceService()
        self.sensor_service = SensorService()
        self.display_service = DisplayService()

        # Aggregated data to send to mobile app
        self.hub_data = PiHubData()

        # Running state
        self._running = False

    async def start(self):
        """Start all services"""
        log_info("Main", "Starting Pi Hub...")

        # Register callbacks before starting services
        self._register_callbacks()

        # Start all services
        await self.ble_service.start()
        await self.wifi_service.start()
        await self.camera_service.start()
        await self.voice_service.start()
        await self.sensor_service.start()
        await self.display_service.start()

        self._running = True
        log_info("Main", "All services started")

        # Start main loop
        await self._main_loop()

    async def stop(self):
        """Stop all services gracefully"""
        log_info("Main", "Stopping Pi Hub...")
        self._running = False

        await self.ble_service.stop()
        await self.wifi_service.stop()
        await self.camera_service.stop()
        await self.voice_service.stop()
        await self.sensor_service.stop()
        await self.display_service.stop()

        log_info("Main", "All services stopped")

    def _register_callbacks(self):
        """Register callbacks for all services"""

        # Sensor readings -> update hub data and display
        def on_sensor_reading(reading: dict):
            self.hub_data.temperature = reading.get("temperature", 0)
            self.hub_data.humidity = reading.get("humidity", 0)
            self.display_service.show_temperature(
                self.hub_data.temperature,
                self.hub_data.humidity
            )

        # TODO: Implement on_reading callback in SensorService
        # self.sensor_service.on_reading(on_sensor_reading)

        # ESP32 data -> update hub data
        def on_esp32_data(data: dict):
            self.hub_data.pressure = data.get("pressure", 0)
            self.hub_data.motion_detected = data.get("motion_detected", False)
            self.hub_data.latitude = data.get("latitude", 0)
            self.hub_data.longitude = data.get("longitude", 0)
            self.hub_data.is_playing_sound = data.get("is_playing_sound", False)
            self.hub_data.esp32_connected = True

        # TODO: Implement on_data_received callback in WiFiService
        # self.wifi_service.on_data_received(on_esp32_data)

        # Face recognition -> update hub data and display
        def on_face_detected(name: str, confidence: float):
            self.hub_data.face_recognized = True
            self.hub_data.face_name = name
            self.display_service.show_face_recognized(name)

        # TODO: Implement on_face_detected callback in CameraService
        # self.camera_service.on_face_detected(on_face_detected)

        # Voice commands -> handle actions
        def on_voice_command(action: str, text: str):
            self._handle_voice_command(action)

        # TODO: Implement on_command_recognized callback in VoiceService
        # self.voice_service.on_command_recognized(on_voice_command)

        # BLE data from mobile app -> handle commands
        def on_mobile_data(data: dict):
            command = MobileCommand.from_dict(data)
            self._handle_mobile_command(command)

        # TODO: Implement on_data_received callback in BLEService
        # self.ble_service.on_data_received(on_mobile_data)

    def _handle_voice_command(self, action: str):
        """Handle voice commands"""
        log_info("Main", f"Handling voice command: {action}")

        if action == "play_calming":
            asyncio.create_task(
                self.wifi_service.send_to_esp32({"command": "play_sound"})
            )
        elif action == "stop_all":
            asyncio.create_task(
                self.wifi_service.send_to_esp32({"command": "stop_sound"})
            )
        elif action == "get_status":
            self.display_service.show_status(
                f"Temp: {self.hub_data.temperature}°C"
            )
        elif action == "trigger_help":
            self.display_service.show_alert("Help requested!")

    async def _handle_mobile_command(self, command: MobileCommand):
        """Handle commands from mobile app"""
        log_info("Main", f"Handling mobile command: {command.command}")

        if command.command == "play_sound":
            await self.wifi_service.send_to_esp32({"command": "play_sound"})

        elif command.command == "stop_sound":
            await self.wifi_service.send_to_esp32({"command": "stop_sound"})

        elif command.command == "get_status":
            await self.ble_service.send_data(self.hub_data.to_dict())

        elif command.command == "start_stream":
            await self.camera_service.start_livestream()

        elif command.command == "stop_stream":
            await self.camera_service.stop_livestream()

    async def _main_loop(self):
        """Main loop - sends aggregated data to mobile app periodically"""
        while self._running:
            try:
                # Update status flags
                self.hub_data.camera_active = self.camera_service.is_running
                self.hub_data.voice_active = self.voice_service.is_listening
                self.hub_data.esp32_connected = self.wifi_service.is_connected

                # Send aggregated data to mobile app via BLE
                await self.ble_service.send_data(self.hub_data.to_dict())

            except Exception as e:
                log_error("Main", f"Error in main loop: {e}")

            await asyncio.sleep(BLE_SEND_INTERVAL)


async def main():
    """Entry point"""
    hub = PiHub()

    # Handle shutdown signals
    loop = asyncio.get_event_loop()

    def shutdown():
        asyncio.create_task(hub.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown)

    try:
        await hub.start()
    except KeyboardInterrupt:
        await hub.stop()


if __name__ == "__main__":
    asyncio.run(main())
