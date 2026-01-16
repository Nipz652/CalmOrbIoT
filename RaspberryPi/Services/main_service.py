#!/usr/bin/env python3
"""
Main Service - Runs all services together

This is the main entry point that:
1. Starts the distress response service (ESP32 UDP listener + display)
2. Starts the BLE GATT service (mobile app control)
3. Starts the BLE beacon scanner (ESP32 proximity detection)
"""

import asyncio
import threading
import signal
import sys

# Import services
from services.distress_service import (
    start_listener,
    display_logo,
    stop_current_animation,
    set_on_esp32_data_callback,
    set_on_distress_callback,
    is_child_profile_active,
)
from services.ble_service import create_ble_service
from services.ble_beacon_service import BLEBeaconService, BeaconConfig, ProximityZone
from services.camera_service import create_camera_service, BehaviorDetection, DISTRESS_BEHAVIORS
from services.streaming_service import create_streaming_service, StreamState
from services.sensor_service import SensorService
from services.voice_service import VoiceService, VoiceState
from services.noise_monitor_service import NoiseMonitorService

# Import settings
try:
    from config.settings import (
        ESP32_BEACON_NAME,
        ESP32_TX_POWER_AT_1M,
        BEACON_RSSI_NEAR,
        BEACON_RSSI_MEDIUM,
        BEACON_RSSI_FAR,
        BEACON_SCAN_INTERVAL,
        BEACON_SCAN_DURATION,
        BEACON_RSSI_SAMPLES,
        BEACON_LOST_TIMEOUT,
        BEACON_ZONE_DEBOUNCE,
    )
except ImportError:
    # Default values if settings not available
    ESP32_BEACON_NAME = "ESP32-StressBall"
    ESP32_TX_POWER_AT_1M = -59
    BEACON_RSSI_NEAR = -60
    BEACON_RSSI_MEDIUM = -75
    BEACON_RSSI_FAR = -85
    BEACON_SCAN_INTERVAL = 2.0
    BEACON_SCAN_DURATION = 2.0
    BEACON_RSSI_SAMPLES = 5
    BEACON_LOST_TIMEOUT = 10.0
    BEACON_ZONE_DEBOUNCE = 3


# BLE Notification Configuration
BLE_NOTIFICATION_INTERVAL = 5.0  # Send BLE notifications every 5 seconds


class MainService:
    """Coordinates all services."""

    def __init__(self):
        self.ble_service = None
        self.beacon_service = None
        self.camera_service = None
        self.streaming_service = None  # Live video/audio streaming
        self.distress_thread = None
        self.camera_task = None
        self.notification_task = None  # BLE periodic notification task
        self.running = False
        self.sensor_service = None
        self.voice_service = None  # Voice command service (Atom Echo)
        self.voice_task = None  # Voice listening loop task
        self.noise_monitor_service = None  # Environmental noise monitor (INMP441 I2S)

        # Child profile state - controls optional services
        self._optional_services_running = False

        # Current proximity state (shared with other services)
        self.current_zone = ProximityZone.UNKNOWN
        self.current_distance = -1.0

        # Current behavior detection (shared with BLE)
        self.current_behavior = "none"
        self.current_confidence = 0.0

        # Current distress state (from ESP32)
        self.current_distress_alert = "none"
        self.current_distress_type = "none"

        # Temperature (will be updated from sensor service if available)
        self.current_temperature = 0.0

        # Environmental noise (will be updated from noise monitor service if available)
        self.current_noise_level = 0.0  # dB level
        self.current_noise_category = "quiet"  # Noise category

        # Data aggregation buffers (collect over 5-second interval)
        self._pressure_buffer = []      # Collect pressure values
        self._motion_buffer = []        # Collect motion values
        self._behavior_buffer = []      # Collect behavior labels

    def _aggregate_pressure(self) -> float:
        """Get average pressure over 5 seconds, or 0 if no values.

        Divides by 5 (the interval) regardless of how many readings were collected.
        """
        if not self._pressure_buffer:
            return 0.0
        return sum(self._pressure_buffer) / 5

    def _aggregate_most_frequent(self, buffer: list) -> str:
        """Get most frequent value from buffer, first occurrence wins on ties.

        Args:
            buffer: List of values collected over 5-second interval

        Returns:
            Most frequent value, or "none" if buffer is empty or all values are "none"
        """
        if not buffer:
            return "none"
        # Filter out "none" values for frequency counting
        valid_values = [v for v in buffer if v != "none"]
        if not valid_values:
            return "none"
        # Count occurrences
        from collections import Counter
        counts = Counter(valid_values)
        max_count = max(counts.values())
        # Return first value with max count (preserves first-seen order)
        for value in valid_values:
            if counts[value] == max_count:
                return value
        return "none"

    def _on_esp32_data(self, parsed_data: dict):
        """Handle ESP32 sensor data received via UDP.

        This callback is called for every ESP32 message received.
        Updates the BLE sensor data for mobile app.
        """
        try:
            # Extract sensor values from parsed ESP32 data
            pressure = float(parsed_data.get("psi_max", 0.0))
            grip_state = parsed_data.get("grip_state", "None")
            motion = parsed_data.get("motion", "None")
            alert = parsed_data.get("alert", "")
            dominant_type = parsed_data.get("dominant_type", "none")

            # Map grip_state to pressureType
            pressure_type_map = {
                "None": "none",
                "Calm": "light",
                "Moderate": "moderate",
                "Stressed": "firm",
                "Tantrum": "squeeze",
            }
            pressure_type = pressure_type_map.get(grip_state, "none")

            # Map motion to standardized format for regular motion field
            motion_map = {
                "None": "none",
                "Still": "none",
                "Gentle Movement": "gentle",
                "Tremble": "tremble",
                "Shake": "shake",
                "ViolentShake": "shake",
                "Impact": "impact",
                "FreeFall": "freefall",
                "Bounce": "bounce",
                "Spinning": "spinning",
                "Rocking": "rocking",
            }
            mapped_motion = motion_map.get(motion, motion.lower() if motion else "none")

            # Map for distressMotion - preserves all 8 motion types
            distress_motion_map = {
                "None": "none",
                "Still": "none",
                "FreeFall": "freefall",
                "Tremble": "tremble",
                "ViolentShake": "shake",
                "Impact": "impact",
                "Bounce": "bounce",
                "Spinning": "spinning",
                "Rocking": "rocking",
            }

            # Determine distress alert from ESP32 data
            distress_alert = "none"
            distress_type = "none"
            distress_motion = "none"
            if "PATTERN_3GRIP" in alert:
                distress_alert = "PATTERN_3GRIP"
                distress_type = dominant_type if dominant_type else "Unknown"
                distress_motion = "none"  # No motion for grip alerts
            elif "MOTION_3X" in alert:
                distress_alert = "MOTION_3X"
                distress_type = dominant_type if dominant_type else grip_state
                # Extract motion type from ESP32 data (motion_type field or current motion)
                motion_type_raw = parsed_data.get("motion_type", motion)
                distress_motion = distress_motion_map.get(motion_type_raw, motion_type_raw.lower() if motion_type_raw else "none")

            # Update BLE sensor data (keeps current state for distress handling)
            if self.ble_service and self.ble_service.service:
                self.ble_service.service.update_sensor_data(
                    pressure=pressure,
                    pressure_type=pressure_type,
                    temperature=self.current_temperature,
                    motion=mapped_motion,
                    proximity_zone=self.current_zone.value,
                    distress_alert=distress_alert,
                    distress_type=distress_type,
                    distress_motion=distress_motion,
                    environmental_noise=self.current_noise_level,
                    noise_level=self.current_noise_category,
                )

            # Collect data for 5-second aggregation
            self._pressure_buffer.append(pressure)
            self._motion_buffer.append(mapped_motion)

        except Exception as e:
            print(f"[Main] Error processing ESP32 data: {e}")

    def _on_distress_detected(self, alert_type: str, distress_type: str, reason: str, distress_motion: str = "none"):
        """Handle distress signal detected from ESP32.

        This callback is called when ESP32 sends a distress alert.
        Updates the BLE service and sends IMMEDIATE notification to mobile app.

        Args:
            alert_type: Type of alert (PATTERN_3GRIP or MOTION_3X)
            distress_type: Dominant grip type (Stressed, Tantrum)
            reason: Human-readable description
            distress_motion: Motion type for MOTION_3X alerts (impact, shake, etc.)
        """
        self.current_distress_alert = alert_type
        self.current_distress_type = distress_type
        print(f"[Main] DISTRESS ALERT: {alert_type} - Type: {distress_type} - Motion: {distress_motion} - {reason}")

        # Update BLE distress data and send IMMEDIATE notification
        if self.ble_service and self.ble_service.service:
            self.ble_service.service.update_distress_data(alert_type, distress_type, distress_motion)
            # Send immediate BLE notification on distress (don't wait for periodic)
            self.ble_service.service.notify_sensor_data()
            print(f"[Main] Sent immediate BLE notification for distress alert")

    def _on_dht22_reading(self, reading: dict):
        """Handle DHT22 temperature/humidity readings."""
        try:
            temperature = reading.get("temperature")

            if temperature is not None:
                self.current_temperature = temperature
                # Update BLE sensor payload with latest temperature
                if self.ble_service and self.ble_service.service:
                    self.ble_service.service.update_sensor_data(
                        pressure=self.ble_service.service._sensor_data["pressure"],
                        pressure_type=self.ble_service.service._sensor_data["pressureType"],
                        temperature=temperature,
                        motion=self.ble_service.service._sensor_data["motion"],
                        proximity_zone=self.current_zone.value,
                        distress_alert=self.ble_service.service._sensor_data["distressAlert"],
                        distress_type=self.ble_service.service._sensor_data["distressType"],
                        distress_motion=self.ble_service.service._sensor_data["distressMotion"],
                        environmental_noise=self.current_noise_level,
                        noise_level=self.current_noise_category,
                    )
        except Exception as e:
            print(f"[Main] Error processing DHT22 data: {e}")

    def _on_noise_reading(self, reading: dict):
        """Handle environmental noise readings from I2S microphone."""
        try:
            db_level = reading.get("db_level", 0.0)
            category = reading.get("category", "quiet")

            self.current_noise_level = db_level
            self.current_noise_category = category

            # Update BLE sensor data with latest noise reading
            if self.ble_service and self.ble_service.service:
                current = self.ble_service.service._sensor_data
                self.ble_service.service.update_sensor_data(
                    pressure=current["pressure"],
                    pressure_type=current["pressureType"],
                    temperature=self.current_temperature,
                    motion=current["motion"],
                    proximity_zone=self.current_zone.value,
                    distress_alert=current["distressAlert"],
                    distress_type=current["distressType"],
                    distress_motion=current["distressMotion"],
                    environmental_noise=db_level,
                    noise_level=category,
                )
        except Exception as e:
            print(f"[Main] Error processing noise data: {e}")

    def _on_high_noise_alert(self, reading: dict):
        """Handle high noise alerts (>85 dB threshold).

        Sends immediate BLE notification to mobile app when environmental noise exceeds threshold.
        """
        try:
            db_level = reading.get("db_level", 0.0)
            category = reading.get("category", "quiet")
            print(f"[Main] HIGH NOISE ALERT: {db_level:.1f} dB ({category})")

            # Send immediate BLE notification (don't wait for periodic interval)
            if self.ble_service and self.ble_service.service:
                self.ble_service.service.notify_sensor_data()
                print(f"[Main] Sent immediate BLE notification for high noise alert")
        except Exception as e:
            print(f"[Main] Error processing high noise alert: {e}")

    async def _run_ble_notification_loop(self):
        """Periodic BLE notification loop.

        Sends aggregated sensor and behavior data to mobile app every BLE_NOTIFICATION_INTERVAL seconds.
        Data is aggregated over the 5-second interval:
        - Pressure: Average (sum/5), or 0 if no values
        - Motion: Most frequent, first occurrence wins on ties, "none" if empty
        - Behavior: Most frequent, first occurrence wins on ties, "none" if empty
        """
        print(f"[Main] Starting BLE notification loop (every {BLE_NOTIFICATION_INTERVAL}s)")

        while self.running:
            try:
                await asyncio.sleep(BLE_NOTIFICATION_INTERVAL)

                if not self.running:
                    break

                # Send BLE notifications if service is available
                if self.ble_service and self.ble_service.service and self.ble_service.is_running:
                    # Aggregate data from 5-second collection buffers
                    aggregated_pressure = self._aggregate_pressure()
                    aggregated_motion = self._aggregate_most_frequent(self._motion_buffer)
                    aggregated_behavior = self._aggregate_most_frequent(self._behavior_buffer)

                    # Get current state from BLE service for non-aggregated fields
                    current_data = self.ble_service.service._sensor_data

                    # Update BLE sensor data with aggregated values
                    self.ble_service.service.update_sensor_data(
                        pressure=aggregated_pressure,
                        pressure_type=current_data.get("pressureType", "none"),
                        temperature=self.current_temperature,
                        motion=aggregated_motion,
                        proximity_zone=self.current_zone.value,
                        distress_alert="none",  # Clear distress for periodic (already sent immediately)
                        distress_type="none",
                        distress_motion="none",
                        environmental_noise=self.current_noise_level,
                        noise_level=self.current_noise_category,
                    )

                    # Update BLE behavior data with aggregated value
                    self.ble_service.service.update_behavior_data(
                        aggregated_behavior,
                        self.current_confidence if aggregated_behavior != "none" else 0.0
                    )

                    # Clear aggregation buffers for next interval
                    self._pressure_buffer.clear()
                    self._motion_buffer.clear()
                    self._behavior_buffer.clear()

                    # Send sensor, behavior, and status data
                    self.ble_service.service.notify_all()
                    self.ble_service.service.notify_status()  # Send esp32_connected status
                    print(f"[Main] Sent periodic BLE notification (aggregated: pressure={aggregated_pressure:.2f}, motion={aggregated_motion}, behavior={aggregated_behavior})")

            except asyncio.CancelledError:
                print("[Main] BLE notification loop cancelled")
                break
            except Exception as e:
                print(f"[Main] BLE notification error: {e}")
                # Continue loop even on error
                await asyncio.sleep(1)

        print("[Main] BLE notification loop stopped")

    def start_distress_listener(self):
        """Run distress listener in a separate thread."""
        try:
            start_listener()
        except Exception as e:
            print(f"[Main] Distress listener error: {e}")

    def _on_zone_change(self, old_zone: ProximityZone, new_zone: ProximityZone):
        """Handle proximity zone changes."""
        self.current_zone = new_zone
        print(f"[Main] Proximity zone: {old_zone.value} -> {new_zone.value}")

        # Update BLE sensor data with new proximity zone
        if self.ble_service and self.ble_service.service:
            self.ble_service.service.update_proximity_zone(new_zone.value)

        # Alert if child is too far
        if new_zone == ProximityZone.OUT_OF_RANGE:
            print("[Main] WARNING: Child may be too far from base station!")
            # Could trigger an alert here (e.g., notify via BLE to mobile app)

        elif new_zone == ProximityZone.FAR:
            print("[Main] NOTICE: Child is moving away from base station")

    def _on_beacon_lost(self):
        """Handle ESP32 beacon lost."""
        print("[Main] ESP32 beacon lost - device may be out of range or powered off")
        self.current_zone = ProximityZone.OUT_OF_RANGE
        # Update BLE sensor data
        if self.ble_service and self.ble_service.service:
            self.ble_service.service.update_proximity_zone("OUT_OF_RANGE")

    def _on_behavior_detected(self, detection: BehaviorDetection):
        """Handle behavior detection from camera."""
        self.current_behavior = detection.label
        self.current_confidence = detection.confidence
        print(f"[Main] Behavior detected: {detection.label} ({detection.confidence:.2f})")

        # Update BLE behavior data (keeps current state for immediate access)
        if self.ble_service and self.ble_service.service:
            self.ble_service.service.update_behavior_data(detection.label, detection.confidence)

        # Collect data for 5-second aggregation
        self._behavior_buffer.append(detection.label)

    def _on_distress_behavior(self, detection: BehaviorDetection):
        """Handle distress behavior detection (may trigger calming response)."""
        print(f"[Main] DISTRESS BEHAVIOR: {detection.label} ({detection.confidence:.2f})")
        # Could trigger animation here similar to ESP32 distress signal
        # For now, just log it - can be expanded later

    def _on_stream_state_change(self, state: StreamState):
        """Handle streaming state changes."""
        print(f"[Main] Stream state changed: {state.name}")

        # Notify mobile app via BLE
        if self.ble_service and self.ble_service.service and self.streaming_service:
            status = self.streaming_service.get_status_dict()
            self.ble_service.service._notify_stream_status(status)

    def _on_voice_command(self, action: str, text: str):
        """Handle voice commands detected by voice service.

        Args:
            action: Command action (play_music, play_animation, play_both)
            text: Raw recognized text
        """
        print(f"[Main] Voice command: {action}")
        # The voice service already executes the command via distress_service
        # This callback is for additional handling (e.g., BLE notification)

    def _on_voice_state_change(self, state: VoiceState):
        """Handle voice service state changes.

        Args:
            state: New voice state (IDLE, READY, PROCESSING)
        """
        print(f"[Main] Voice state: {state.value}")

    def _create_beacon_config(self) -> BeaconConfig:
        """Create beacon configuration from settings."""
        return BeaconConfig(
            device_name=ESP32_BEACON_NAME,
            tx_power_at_1m=ESP32_TX_POWER_AT_1M,
            rssi_near=BEACON_RSSI_NEAR,
            rssi_medium=BEACON_RSSI_MEDIUM,
            rssi_far=BEACON_RSSI_FAR,
            scan_interval=BEACON_SCAN_INTERVAL,
            scan_duration=BEACON_SCAN_DURATION,
            rssi_samples=BEACON_RSSI_SAMPLES,
            lost_timeout=BEACON_LOST_TIMEOUT,
            zone_change_threshold=BEACON_ZONE_DEBOUNCE,
        )

    async def wait_for_bluetooth_ready(self, timeout=20):
        import subprocess
        import time

        print("[Main] Waiting for Bluetooth adapter to be ready...")
        start = time.time()

        while time.time() - start < timeout:
            try:
                output = subprocess.check_output(
                    ["bluetoothctl", "show"],
                    stderr=subprocess.DEVNULL
                ).decode()

                if "Powered: yes" in output:
                    print("[Main] Bluetooth adapter is ready")
                    return True
            except Exception:
                pass

            await asyncio.sleep(1)

        print("[Main] Bluetooth adapter NOT ready after timeout")
        return False

    async def run(self):
        """Run all services."""
        self.running = True

        print("=" * 60)
        print("StressBall Hub - Main Service")
        print("=" * 60)

        # Set up callbacks for ESP32 data BEFORE starting distress listener
        print("[Main] Setting up ESP32 data callbacks...")
        set_on_esp32_data_callback(self._on_esp32_data)
        set_on_distress_callback(self._on_distress_detected)

        # Start distress listener in background thread
        print("[Main] Starting distress listener (UDP from ESP32)...")
        self.distress_thread = threading.Thread(
            target=self.start_distress_listener,
            daemon=True
        )
        self.distress_thread.start()

        # Give distress service time to initialize display
        await asyncio.sleep(2)

        await self.wait_for_bluetooth_ready()
        print("[Main] Starting BLE GATT service (for mobile app)...")
        self.ble_service = create_ble_service()
        import subprocess
        subprocess.run(["bluetoothctl", "power", "on"])
        subprocess.run(["bluetoothctl", "discoverable", "on"])
        subprocess.run(["bluetoothctl", "pairable", "on"])
        await self.ble_service.start()

        # Initialize DHT22 sensor service (but don't start - waits for child profile)
        print("[Main] Initializing DHT22 sensor service (waiting for profile activation)...")
        self.sensor_service = SensorService()
        self.sensor_service.on_reading(self._on_dht22_reading)
        # Note: Not starting - will start when child profile is activated

        # Initialize noise monitor service (but don't start - waits for child profile)
        print("[Main] Initializing noise monitor service (waiting for profile activation)...")
        self.noise_monitor_service = NoiseMonitorService()
        self.noise_monitor_service.on_reading(self._on_noise_reading)
        self.noise_monitor_service.on_high_noise_alert(self._on_high_noise_alert)
        # Note: Not starting - will start when child profile is activated

        # Start BLE beacon scanner (for ESP32 proximity)
        print("[Main] Starting BLE beacon scanner (for ESP32 proximity)...")
        self.beacon_service = BLEBeaconService(self._create_beacon_config())
        self.beacon_service.on_zone_change = self._on_zone_change
        self.beacon_service.on_beacon_lost = self._on_beacon_lost
        await self.beacon_service.start()

        # Initialize camera service (but don't start - waits for child profile)
        print("[Main] Initializing camera service (waiting for profile activation)...")
        self.camera_service = create_camera_service()
        self.camera_service.on_behavior_detected(self._on_behavior_detected)
        self.camera_service.on_distress_behavior(self._on_distress_behavior)
        # Note: Not starting - will start when child profile is activated

        # Start BLE notification loop (sends data to mobile app every 5 seconds)
        print(f"[Main] Starting BLE notification loop (every {BLE_NOTIFICATION_INTERVAL}s)...")
        self.notification_task = asyncio.create_task(self._run_ble_notification_loop())

        # Initialize streaming service (for live video/audio streaming)
        print("[Main] Initializing streaming service...")
        self.streaming_service = create_streaming_service(self.camera_service)
        self.streaming_service.on_state_change(self._on_stream_state_change)

        # Connect streaming service to BLE service
        if self.ble_service and self.ble_service.service:
            self.ble_service.service.set_streaming_service(self.streaming_service)
            self.ble_service.service.set_main_service_callback(self._handle_service_control)
            print("[Main] Streaming service and service control connected to BLE")

        # Initialize and start voice service (always on)
        print("[Main] Initializing voice command service (Atom Echo)...")
        self.voice_service = VoiceService()
        self.voice_service.on_command_recognized(self._on_voice_command)
        self.voice_service.on_state_change(self._on_voice_state_change)

        voice_started = await self.voice_service.start()
        if voice_started:
            self.voice_task = asyncio.create_task(self.voice_service.listen_loop())
            print("[Main] Voice command service started (always on)")
        else:
            print("[Main] Voice command service failed to start (dependencies missing?)")

        print("\n" + "=" * 60)
        print("Core services running!")
        print("- Distress listener: Waiting for ESP32 UDP signals")
        print("- BLE GATT service: Ready for mobile app connection")
        print(f"- BLE notifications: Every {BLE_NOTIFICATION_INTERVAL}s + immediate on distress")
        print(f"- BLE beacon scanner: Scanning for '{ESP32_BEACON_NAME}'")
        if voice_started:
            print("- Voice commands: Listening for 'ORB!' wake word")
        else:
            print("- Voice commands: NOT RUNNING (check dependencies)")
        print("")
        print("Optional services (waiting for child profile activation):")
        print("- Camera service: Initialized, not running")
        print("- Sensor service: Initialized, not running")
        print("- Noise monitor: Initialized, not running")
        print("- Streaming service: Initialized, not running")
        print("=" * 60)
        print("\nPress Ctrl+C to stop all services...")

        # Keep running
        try:
            while self.running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass

    async def _handle_service_control(self, event: str, value):
        """Handle service control events from BLE.

        Args:
            event: Event type ('child_profile')
            value: Event value (bool for child_profile)
        """
        print(f"[Main] [DEBUG] Service control event: {event}={value}")
        if event == 'child_profile':
            if value:
                print("[Main] [DEBUG] Child paired - starting optional services")
                await self._start_optional_services()
            else:
                print("[Main] [DEBUG] Child unpaired - stopping optional services and resetting ESP32")
                await self._stop_optional_services()

    async def _start_optional_services(self):
        """Start optional services (camera, sensor, streaming).

        Called when child profile is activated.
        """
        if self._optional_services_running:
            print("[Main] Optional services already running")
            return

        print("[Main] Starting optional services (child profile activated)...")

        # Start DHT22 sensor service
        if self.sensor_service and not self.sensor_service.is_running:
            print("[Main] Starting DHT22 sensor service...")
            await self.sensor_service.start()

        # Start noise monitor service
        if self.noise_monitor_service and not self.noise_monitor_service.is_running:
            print("[Main] Starting noise monitor service...")
            noise_started = await self.noise_monitor_service.start()
            if noise_started:
                print("[Main] Noise monitor started successfully")
            else:
                print("[Main] Noise monitor failed to start (check I2S configuration)")

        # Start camera service
        if self.camera_service and not self.camera_service.is_running:
            print("[Main] Starting camera service...")
            camera_started = await self.camera_service.start()
            if camera_started:
                self.camera_task = asyncio.create_task(self.camera_service.run_detection_loop())
                print("[Main] Camera behavior detection started")

        # Streaming service is ready but not started until requested
        if self.streaming_service:
            print("[Main] Streaming service ready for requests")

        self._optional_services_running = True
        print("[Main] Optional services started")

    async def _stop_optional_services(self):
        """Stop optional services (camera, sensor, streaming).

        Called when child profile is deactivated.
        """
        if not self._optional_services_running:
            print("[Main] Optional services already stopped")
            return

        print("[Main] Stopping optional services (child profile deactivated)...")

        # Stop streaming first (if active)
        if self.streaming_service and self.streaming_service.is_streaming():
            print("[Main] Stopping streaming service...")
            await self.streaming_service.stop_streaming()

        # Stop camera service
        if self.camera_task:
            self.camera_task.cancel()
            try:
                await self.camera_task
            except asyncio.CancelledError:
                pass
            self.camera_task = None
        if self.camera_service and self.camera_service.is_running:
            await self.camera_service.stop()
            print("[Main] Camera service stopped")

        # Stop sensor service
        if self.sensor_service and self.sensor_service.is_running:
            await self.sensor_service.stop()
            print("[Main] Sensor service stopped")

        # Stop noise monitor service
        if self.noise_monitor_service and self.noise_monitor_service.is_running:
            await self.noise_monitor_service.stop()
            print("[Main] Noise monitor service stopped")

        # Reset ESP32 and Pi to default settings when child unpairs
        from services.distress_service import set_volume, set_sound, set_animation, stop_current_animation
        print("[Main] Resetting to default settings (child unpaired)...")

        # Stop any playing animations
        stop_current_animation()

        # Reset to defaults
        set_volume(30)  # Reset to maximum volume
        set_sound(1)    # Reset to default sound
        set_animation(1)  # Reset to default animation

        print("[Main] Reset complete: volume=30, sound=1, animation=1")

        self._optional_services_running = False
        print("[Main] Optional services stopped")

    async def stop(self):
        """Stop all services."""
        print("\n[Main] Stopping all services...")
        self.running = False

        # Stop streaming service first (restores Wi-Fi if AP mode was active)
        if self.streaming_service and self.streaming_service.is_streaming():
            print("[Main] Stopping streaming service...")
            await self.streaming_service.stop_streaming()

        # Stop voice service
        if self.voice_task:
            self.voice_task.cancel()
            try:
                await self.voice_task
            except asyncio.CancelledError:
                pass
            self.voice_task = None
        if self.voice_service:
            await self.voice_service.stop()
            print("[Main] Voice service stopped")

        # Stop BLE notification loop
        if self.notification_task:
            self.notification_task.cancel()
            try:
                await self.notification_task
            except asyncio.CancelledError:
                pass
            print("[Main] BLE notification loop stopped")

        # Stop camera service
        if self.camera_task:
            self.camera_task.cancel()
            try:
                await self.camera_task
            except asyncio.CancelledError:
                pass
        if self.camera_service:
            await self.camera_service.stop()

        # Stop beacon scanner
        if self.beacon_service:
            await self.beacon_service.stop()

        # Stop BLE GATT
        if self.ble_service:
            await self.ble_service.stop()

        # Stop animation and show logo
        stop_current_animation()
        display_logo()

        print("[Main] All services stopped")

    def get_proximity_data(self) -> dict:
        """Get current proximity data (for BLE transmission to mobile app)."""
        if self.beacon_service:
            data = self.beacon_service.get_beacon_data()
            return data.to_dict()
        return {
            "detected": False,
            "zone": "UNKNOWN",
            "distance_meters": -1,
        }


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    print("\n[Main] Received shutdown signal...")
    sys.exit(0)


async def main():
    """Main entry point."""
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    service = MainService()

    try:
        await service.run()
    except KeyboardInterrupt:
        pass
    finally:
        await service.stop()


if __name__ == "__main__":
    asyncio.run(main())
