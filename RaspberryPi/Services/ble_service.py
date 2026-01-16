#!/usr/bin/env python3
"""
BLE Service - Bluetooth Low Energy peripheral for mobile app communication

Uses bluez-peripheral library (compatible with Python 3.13)

Allows mobile app to:
- Change animation selection (1-5)
- Change sound selection (1-13)
- Trigger "Find My Device" (plays alarm sound 14)
- Get current settings
- Enable/disable animation and sound responses
"""

import asyncio
import json
from typing import Optional

# ======================
# Patch dbus_next introspection bug (BlueZ 5.x compatibility)
# ======================
try:
    import dbus_next.introspection as _intr

    _original_arg_from_xml = _intr.Arg.from_xml

    @staticmethod
    def _patched_arg_from_xml(element, direction='in'):
        try:
            return _original_arg_from_xml(element, direction)
        except _intr.InvalidIntrospectionError as e:
            if 'type' in str(e):
                # Return a proper Arg object for malformed introspection
                # Arg(signature, direction, name)
                name = element.attrib.get('name', None)
                signature = element.attrib.get('type', 's')  # Default to string
                return _intr.Arg(signature, direction, name)
            raise

    _intr.Arg.from_xml = _patched_arg_from_xml
except ImportError:
    pass  # dbus_next not installed yet

# Import bluez-peripheral for BLE GATT server
try:
    from bluez_peripheral.gatt.service import Service
    from bluez_peripheral.gatt.characteristic import characteristic, CharacteristicFlags as CharFlags
    from bluez_peripheral.advert import Advertisement
    from bluez_peripheral.agent import NoIoAgent
    from bluez_peripheral.util import get_message_bus, Adapter
    BLUEZ_AVAILABLE = True
except ImportError as e:
    BLUEZ_AVAILABLE = False
    print(f"[BLE] Warning: 'bluez-peripheral' not available: {e}")

# Import distress service functions
from services.distress_service import (
    set_animation,
    set_sound,
    find_my_device,
    enable_animation,
    enable_sound,
    get_settings,
    get_full_settings,
    stop_sound,
    play_sound,
    play_animation_now,
    SOUNDS,
    ANIMATIONS,
    set_on_esp32_data_callback,
    set_on_distress_callback,
    set_child_profile_active,
    is_child_profile_active,
)


# ======================
# BLE Configuration
# ======================

BLE_DEVICE_NAME = "Calm Orb Hub"

# Custom UUIDs for the service
SERVICE_UUID = "12345678-1234-5678-1234-56789abcdef0"

# Characteristic UUIDs
CHAR_SETTINGS_UUID = "12345678-1234-5678-1234-56789abcdef1"      # Read/Write settings
CHAR_COMMAND_UUID = "12345678-1234-5678-1234-56789abcdef2"       # Write commands
CHAR_STATUS_UUID = "12345678-1234-5678-1234-56789abcdef3"        # Read status (notify)
CHAR_SENSOR_UUID = "12345678-1234-5678-1234-56789abcdef4"        # Sensor data (notify)
CHAR_EMOTION_UUID = "12345678-1234-5678-1234-56789abcdef5"       # Emotion data (notify)

# Command codes from mobile app
CMD_SET_ANIMATION = 0x01
CMD_SET_SOUND = 0x02
CMD_FIND_DEVICE = 0x03
CMD_ENABLE_ANIMATION = 0x04
CMD_ENABLE_SOUND = 0x05
CMD_STOP_SOUND = 0x06
CMD_GET_SETTINGS = 0x07
CMD_PLAY_SOUND = 0x08  # Play specific sound on ESP32
CMD_PLAY_ANIMATION = 0x09  # Play animation immediately on TFT display
CMD_SET_VOLUME = 0x0A

# Live streaming commands
CMD_START_LIVE_STREAM = 0x10
CMD_STOP_LIVE_STREAM = 0x11
CMD_GET_STREAM_STATUS = 0x12
CMD_GET_AP_CREDENTIALS = 0x13

# Child profile control
CMD_SET_CHILD_PROFILE = 0x14  # Enable/disable child profile (0=off, 1=on)


class StressBallService(Service):
    """BLE GATT Service for StressBall Hub using bluez-peripheral."""

    def __init__(self):
        super().__init__(SERVICE_UUID, True)  # True = primary service
        self._status_value = b""
        self._notify_callback = None

        # Streaming service reference (set by main_service)
        self._streaming_service = None

        # Main service callback for service control (child profile toggle)
        self._main_service_callback = None

        # Default sensor data payload
        self._sensor_data = {
            "type": "sensor",
            "deviceId": "orb-01",
            "sessionId": "",
            "childId": "",
            "timestamp": "",
            "pressure": 0.0,
            "pressureType": "none",
            "temperature": 0.0,
            "motion": "none",
            "proximityZone": "UNKNOWN",  # NEAR, MEDIUM, FAR, OUT_OF_RANGE, UNKNOWN
            "distressAlert": "none",  # PATTERN_3GRIP, MOTION_3X, or none
            "distressType": "none",  # Stressed, Tantrum, or none (dominant grip type)
            "distressMotion": "none",  # Motion type for MOTION_3X alerts (impact, shake, bounce, etc.)
            "environmentalNoise": 0.0,  # dB level (float)
            "noiseLevel": "quiet",  # silent, quiet, moderate, loud, very_loud
        }

        # Default behavior data payload (Roboflow autism behavior detection)
        # Model: https://universe.roboflow.com/asddetection/autism-ximav
        # Classes: Aggressive_Behavior, Avoid_Eye_Contact, Covering_Ears, Finger_Bitting,
        #          Finger_Flicking, Hand_Clapping, Hand_Flapping, Head_Banging, Holding_Item,
        #          Jumping, SIB_Bitting, Shaking_Legs, Toe_Walking, Tpot_Stimming, Twirling,
        #          Weird_Expression
        self._emotion_data = {
            "type": "behavior",
            "deviceId": "orb-01",
            "sessionId": "",
            "childId": "",
            "timestamp": "",
            "behaviorLabel": "none",  # One of the 16 Roboflow classes or "none"
            "confidence": 0.0,
        }

        # Session context
        self._session_id = ""
        self._child_id = ""

    def set_session_context(self, session_id: str, child_id: str):
        """Set the current session and child ID."""
        self._session_id = session_id
        self._child_id = child_id
        self._sensor_data["sessionId"] = session_id
        self._sensor_data["childId"] = child_id
        self._emotion_data["sessionId"] = session_id
        self._emotion_data["childId"] = child_id

    def set_streaming_service(self, streaming_service):
        """Set the streaming service reference for live streaming commands."""
        self._streaming_service = streaming_service

    def set_main_service_callback(self, callback):
        """Set callback for main service control (e.g., child profile toggle).

        Callback signature: callback(event: str, value: Any)
        Events:
            - 'child_profile': value is bool (True=activate, False=deactivate)
        """
        self._main_service_callback = callback

    def update_sensor_data(self, pressure: float, pressure_type: str, temperature: float, motion: str, proximity_zone: str = "UNKNOWN", distress_alert: str = "none", distress_type: str = "none", distress_motion: str = "none", environmental_noise: float = 0.0, noise_level: str = "quiet"):
        """Update sensor data payload.

        Args:
            pressure: Pressure value in PSI
            pressure_type: Type of grip (none, light, moderate, firm, stress, tantrum)
            temperature: Temperature in Celsius
            motion: Motion type (None, Impact, ViolentShake, FreeFall, Bounce, Spinning, Rocking, Tremble)
            proximity_zone: Proximity zone (NEAR, MEDIUM, FAR, OUT_OF_RANGE, UNKNOWN)
            distress_alert: Distress alert type (PATTERN_3GRIP, MOTION_3X, or none)
            distress_type: Dominant grip type (Stressed, Tantrum, or none)
            distress_motion: Motion type that triggered MOTION_3X alert (impact, shake, bounce, etc.)
            environmental_noise: Environmental noise level in dB
            noise_level: Noise category (silent, quiet, moderate, loud, very_loud)
        """
        from datetime import datetime
        self._sensor_data["pressure"] = pressure
        self._sensor_data["pressureType"] = pressure_type
        self._sensor_data["temperature"] = temperature
        self._sensor_data["motion"] = motion
        self._sensor_data["proximityZone"] = proximity_zone
        self._sensor_data["distressAlert"] = distress_alert
        self._sensor_data["distressType"] = distress_type
        self._sensor_data["distressMotion"] = distress_motion
        self._sensor_data["environmentalNoise"] = environmental_noise
        self._sensor_data["noiseLevel"] = noise_level
        self._sensor_data["timestamp"] = datetime.now().isoformat() + "Z"
        self._sensor_data["sessionId"] = self._session_id
        self._sensor_data["childId"] = self._child_id

    def update_proximity_zone(self, proximity_zone: str):
        """Update proximity zone only."""
        self._sensor_data["proximityZone"] = proximity_zone

    def update_distress_data(self, distress_alert: str, distress_type: str, distress_motion: str = "none"):
        """Update distress alert data from ESP32.

        Args:
            distress_alert: Type of distress alert:
                - "PATTERN_3GRIP": 3 grips beyond stress threshold within 3s gaps
                - "MOTION_3X": 3 consecutive same motions detected
                - "none": No distress alert
            distress_type: Dominant grip type during distress:
                - "Stressed": Grip PSI 2.0-4.0
                - "Tantrum": Grip PSI > 4.0
                - "none": No distress type
            distress_motion: Motion type that triggered MOTION_3X alert:
                - "impact", "shake", "bounce", "spinning", "rocking", etc.
                - "none": No motion (for PATTERN_3GRIP or no alert)
        """
        self._sensor_data["distressAlert"] = distress_alert
        self._sensor_data["distressType"] = distress_type
        self._sensor_data["distressMotion"] = distress_motion

    def clear_distress_data(self):
        """Clear distress alert data (call after distress is handled)."""
        self._sensor_data["distressAlert"] = "none"
        self._sensor_data["distressType"] = "none"
        self._sensor_data["distressMotion"] = "none"

    def update_behavior_data(self, behavior_label: str, confidence: float):
        """Update behavior data payload from Roboflow autism detection.

        Args:
            behavior_label: One of the 16 Roboflow classes or "none":
                - Aggressive_Behavior, Avoid_Eye_Contact, Covering_Ears, Finger_Bitting,
                - Finger_Flicking, Hand_Clapping, Hand_Flapping, Head_Banging, Holding_Item,
                - Jumping, SIB_Bitting, Shaking_Legs, Toe_Walking, Tpot_Stimming, Twirling,
                - Weird_Expression
            confidence: Detection confidence (0.0 - 1.0)
        """
        from datetime import datetime
        self._emotion_data["behaviorLabel"] = behavior_label
        self._emotion_data["confidence"] = confidence
        self._emotion_data["timestamp"] = datetime.now().isoformat() + "Z"
        self._emotion_data["sessionId"] = self._session_id
        self._emotion_data["childId"] = self._child_id

    # Keep old method name for backwards compatibility
    def update_emotion_data(self, emotion_label: str, confidence: float):
        """Deprecated: Use update_behavior_data instead."""
        self.update_behavior_data(emotion_label, confidence)

    def get_sensor_payload(self) -> dict:
        """Get current sensor payload."""
        return self._sensor_data.copy()

    def get_behavior_payload(self) -> dict:
        """Get current behavior payload."""
        return self._emotion_data.copy()

    # Keep old method name for backwards compatibility
    def get_emotion_payload(self) -> dict:
        """Deprecated: Use get_behavior_payload instead."""
        return self.get_behavior_payload()

    # ==================
    # BLE Notification Methods
    # ==================
    def notify_sensor_data(self):
        """Send BLE notification with current sensor data.

        Call this to push sensor data to connected mobile app.
        Used for:
        - Periodic updates (every 5 seconds)
        - Immediate updates on distress events
        """
        try:
            from datetime import datetime
            # Update timestamp before sending
            self._sensor_data["timestamp"] = datetime.now().isoformat() + "Z"
            payload = json.dumps(self._sensor_data).encode()
            self.sensor_char.changed(payload)
            return True
        except Exception as e:
            print(f"[BLE] Failed to notify sensor data: {e}")
            return False

    def notify_behavior_data(self):
        """Send BLE notification with current behavior data.

        Call this to push behavior detection data to connected mobile app.
        Used for:
        - Periodic updates (every 5 seconds)
        - Immediate updates on behavior detection
        """
        try:
            from datetime import datetime
            # Update timestamp before sending
            self._emotion_data["timestamp"] = datetime.now().isoformat() + "Z"
            payload = json.dumps(self._emotion_data).encode()
            self.emotion_char.changed(payload)
            return True
        except Exception as e:
            print(f"[BLE] Failed to notify behavior data: {e}")
            return False

    def notify_all(self):
        """Send BLE notifications for both sensor and behavior data.

        Convenience method to send both payloads at once.
        """
        sensor_ok = self.notify_sensor_data()
        behavior_ok = self.notify_behavior_data()
        return sensor_ok and behavior_ok

    def notify_status(self):
        """Send BLE notification with current status/settings.

        Call this to push status data (including esp32_connected) to mobile app.
        Used for:
        - Periodic updates (every 5 seconds with sensor data)
        - When ESP32 connection status changes
        """
        try:
            settings = get_settings()
            payload = json.dumps(settings).encode()
            self.status_char.changed(payload)
            return True
        except Exception as e:
            print(f"[BLE] Failed to notify status: {e}")
            return False

    # ==================
    # Settings Characteristic (Read/Write)
    # ==================
    @characteristic(CHAR_SETTINGS_UUID, CharFlags.READ | CharFlags.WRITE)
    def settings_char(self, options):
        """Read current settings as JSON (full version with animation/sound lists)."""
        settings = get_full_settings()
        return json.dumps(settings).encode()

    @settings_char.setter
    def settings_char(self, value, options):
        """Write settings from mobile app."""
        self._process_settings(value)
        return b""  # Return empty bytes to indicate success

    # ==================
    # Command Characteristic (Write only)
    # ==================
    @characteristic(CHAR_COMMAND_UUID, CharFlags.WRITE | CharFlags.WRITE_WITHOUT_RESPONSE)
    def command_char(self, options):
        """Command characteristic (write-only, return empty on read)."""
        return b""

    @command_char.setter
    def command_char(self, value, options):
        """Process command from mobile app."""
        self._process_command(value)

    # ==================
    # Status Characteristic (Read/Notify)
    # ==================
    @characteristic(CHAR_STATUS_UUID, CharFlags.READ | CharFlags.NOTIFY)
    def status_char(self, options):
        """Read current status as JSON."""
        settings = get_settings()
        return json.dumps(settings).encode()

    # ==================
    # Sensor Data Characteristic (Read/Notify)
    # ==================
    @characteristic(CHAR_SENSOR_UUID, CharFlags.READ | CharFlags.NOTIFY)
    def sensor_char(self, options):
        """Read current sensor data as JSON."""
        return json.dumps(self._sensor_data).encode()

    # ==================
    # Behavior Data Characteristic (Read/Notify) - Roboflow autism detection
    # ==================
    @characteristic(CHAR_EMOTION_UUID, CharFlags.READ | CharFlags.NOTIFY)
    def emotion_char(self, options):
        """Read current behavior data as JSON (from Roboflow autism detection)."""
        return json.dumps(self._emotion_data).encode()

    # ==================
    # Command Processing
    # ==================
    def _process_command(self, data: bytes):
        """Process binary command from mobile app."""
        if len(data) < 1:
            return

        cmd = data[0]
        param = data[1] if len(data) > 1 else 0

        print(f"[BLE] Received command: 0x{cmd:02X}, param: {param}")

        if cmd == CMD_SET_ANIMATION:
            set_animation(param)
        elif cmd == CMD_SET_SOUND:
            set_sound(param)
        elif cmd == CMD_FIND_DEVICE:
            find_my_device()
        elif cmd == CMD_ENABLE_ANIMATION:
            enable_animation(param == 1)
        elif cmd == CMD_ENABLE_SOUND:
            enable_sound(param == 1)
        elif cmd == CMD_STOP_SOUND:
            stop_sound()
        elif cmd == CMD_GET_SETTINGS:
            # Settings will be read via read characteristic
            pass
        elif cmd == CMD_PLAY_SOUND:
            # Play specific sound on ESP32 (mobile app request)
            print(f"[DEBUG] BLE received CMD_PLAY_SOUND with param: {param} from mobile app")
            play_sound(param)
            print(f"[BLE] Mobile app requested play sound {param}")
        elif cmd == CMD_PLAY_ANIMATION:
            # Play animation immediately on TFT display (mobile app request)
            # Distress signals will still take priority
            play_animation_now(param)
            print(f"[BLE] Mobile app requested play animation {param}")
        elif cmd == CMD_SET_VOLUME:
            # Forward volume command to ESP32 via distress_service
            print(f"[BLE] Received CMD_SET_VOLUME with param: {param}")
            from services.distress_service import set_volume
            set_volume(param)
            print(f"[BLE] Volume set to {param}")
        # Live streaming commands
        elif cmd == CMD_START_LIVE_STREAM:
            self._handle_start_stream()
        elif cmd == CMD_STOP_LIVE_STREAM:
            self._handle_stop_stream()
        elif cmd == CMD_GET_STREAM_STATUS:
            self._handle_get_stream_status()
        elif cmd == CMD_GET_AP_CREDENTIALS:
            self._handle_get_ap_credentials()
        # Child profile control
        elif cmd == CMD_SET_CHILD_PROFILE:
            import asyncio
            active = param == 1
            print(f"[BLE] [DEBUG] Received CMD_SET_CHILD_PROFILE: param={param}, active={active}")
            set_child_profile_active(active)
            # Notify main service to start/stop optional services (async callback)
            if self._main_service_callback:
                print(f"[BLE] [DEBUG] Calling main_service_callback with child_profile={active}")
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self._main_service_callback('child_profile', active))
                except RuntimeError:
                    # No event loop running - log warning
                    print("[BLE] WARNING: Cannot update child profile - no event loop running")
            else:
                print("[BLE] [DEBUG] WARNING: main_service_callback not set!")
            print(f"[BLE] Child profile {'activated' if active else 'deactivated'}")

    def _handle_start_stream(self):
        """Handle START_LIVE_STREAM command."""
        import asyncio

        # Check if child profile is active (required for streaming)
        if not is_child_profile_active():
            print("[BLE] Cannot start stream: child profile not active")
            self._notify_stream_status({
                "state": 5,  # ERROR state
                "stateName": "ERROR",
                "errorMessage": "Child profile not active. Activate a child profile first.",
                "apSSID": "",
                "apPassword": "",
                "videoUrl": "",
                "audioUrl": "",
                "videoClients": 0,
                "audioClients": 0,
                "startTime": 0,
                "duration": 0,
            })
            return

        if not self._streaming_service:
            print("[BLE] Streaming service not available")
            self._notify_stream_status({
                "state": 5,  # ERROR state
                "stateName": "ERROR",
                "errorMessage": "Streaming service not initialized",
                "apSSID": "",
                "apPassword": "",
                "videoUrl": "",
                "audioUrl": "",
                "videoClients": 0,
                "audioClients": 0,
                "startTime": 0,
                "duration": 0,
            })
            return

        # Check if camera service is available before starting
        if not self._streaming_service.camera_service:
            print("[BLE] Camera service not available for streaming")
            self._notify_stream_status({
                "state": 5,  # ERROR state
                "stateName": "ERROR",
                "errorMessage": "Camera service not available",
                "apSSID": "",
                "apPassword": "",
                "videoUrl": "",
                "audioUrl": "",
                "videoClients": 0,
                "audioClients": 0,
                "startTime": 0,
                "duration": 0,
            })
            return

        print("[BLE] Starting live stream...")

        async def _start_stream_safe():
            """Wrapper to safely start streaming without crashing BLE."""
            try:
                success = await self._streaming_service.start_streaming()
                if not success:
                    print("[BLE] Streaming failed to start (returned False)")
                    # Status should already be updated by streaming_service
            except Exception as e:
                print(f"[BLE] Error starting stream (BLE stays connected): {e}")
                import traceback
                traceback.print_exc()
                # Notify mobile app of error via status characteristic
                try:
                    self._notify_stream_status({
                        "state": 5,  # ERROR state
                        "stateName": "ERROR",
                        "errorMessage": str(e),
                        "apSSID": "",
                        "apPassword": "",
                        "videoUrl": "",
                        "audioUrl": "",
                        "videoClients": 0,
                        "audioClients": 0,
                        "startTime": 0,
                        "duration": 0,
                    })
                except Exception:
                    pass

        asyncio.create_task(_start_stream_safe())

    def _handle_stop_stream(self):
        """Handle STOP_LIVE_STREAM command."""
        import asyncio
        if not self._streaming_service:
            print("[BLE] Streaming service not available")
            return

        print("[BLE] Stopping live stream...")

        async def _stop_stream_safe():
            """Wrapper to safely stop streaming without crashing BLE."""
            try:
                await self._streaming_service.stop_streaming()
            except Exception as e:
                print(f"[BLE] Error stopping stream (BLE stays connected): {e}")
                import traceback
                traceback.print_exc()

        asyncio.create_task(_stop_stream_safe())

    def _handle_get_stream_status(self):
        """Handle GET_STREAM_STATUS command - sends status via notification."""
        if not self._streaming_service:
            print("[BLE] Streaming service not available")
            return

        status = self._streaming_service.get_status_dict()
        self._notify_stream_status(status)

    def _handle_get_ap_credentials(self):
        """Handle GET_AP_CREDENTIALS command - sends credentials via notification."""
        if not self._streaming_service:
            print("[BLE] Streaming service not available")
            return

        creds = self._streaming_service.get_ap_credentials()
        self._notify_stream_status({"type": "ap_credentials", **creds})

    def _notify_stream_status(self, data: dict):
        """Send stream status/credentials via status characteristic notification."""
        try:
            payload = json.dumps(data).encode()
            self.status_char.changed(payload)
            print(f"[BLE] Sent stream status: {data.get('state', data.get('type', 'unknown'))}")
        except Exception as e:
            print(f"[BLE] Failed to notify stream status: {e}")

    def _process_settings(self, data: bytes):
        """Process settings JSON from mobile app."""
        try:
            # Validate input size (prevent DoS)
            if len(data) > 4096:  # 4KB limit
                raise ValueError(f"Settings payload too large: {len(data)} bytes")

            settings = json.loads(data.decode('utf-8'))
            print(f"[BLE] Received settings: {settings}")

            # Validate it's a dictionary
            if not isinstance(settings, dict):
                raise ValueError("Settings must be a JSON object")

            if "animation" in settings:
                set_animation(settings["animation"])
            if "sound" in settings:
                set_sound(settings["sound"])
            if "animation_enabled" in settings:
                enable_animation(settings["animation_enabled"])
            if "sound_enabled" in settings:
                enable_sound(settings["sound_enabled"])
            if "find_device" in settings and settings["find_device"]:
                find_my_device()
            if "play_sound" in settings:
                print(f"[BLE] [DEBUG] play_sound found in settings: {settings['play_sound']}")
                print(f"[BLE] [DEBUG] This will trigger PLAY command to ESP32!")
                play_sound(settings["play_sound"])
                print(f"[BLE] Mobile app requested play sound {settings['play_sound']}")
            if "child_profile_active" in settings:
                import asyncio
                active = settings["child_profile_active"]
                set_child_profile_active(active)
                # Notify main service to start/stop optional services (async callback)
                if self._main_service_callback:
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(self._main_service_callback('child_profile', active))
                    except RuntimeError:
                        # No event loop running - log warning instead of trying asyncio.run
                        print("[BLE] WARNING: Cannot update child profile - no event loop running")
                        # Still update the state variable even if callback can't be called
                print(f"[BLE] Child profile set via JSON: {'active' if active else 'inactive'}")

        except json.JSONDecodeError as e:
            print(f"[BLE] Invalid JSON in settings: {e}")
            raise  # Let BLE layer handle error response
        except Exception as e:
            print(f"[BLE] Error processing settings: {e}")
            import traceback
            traceback.print_exc()
            raise  # Propagate error to mobile app


class BLEService:
    """BLE Service manager for StressBall Hub."""

    def __init__(self):
        self.bus = None
        self.adapter = None
        self.service = None
        self.advert = None
        self.agent = None
        self.is_running = False

    async def start(self):
        """Start the BLE GATT server."""
        if not BLUEZ_AVAILABLE:
            print("[BLE] Cannot start - 'bluez-peripheral' library not available")
            print("[BLE] Install with: pip install bluez-peripheral")
            return False

        try:
            print("[BLE] Starting BLE GATT server...")

            # Get D-Bus message bus
            self.bus = await get_message_bus()

            # Get Bluetooth adapter - use direct path to avoid introspection issues
            adapter_path = "/org/bluez/hci0"
            try:
                self.adapter = await Adapter.get_first(self.bus)
                adapter_path = self.adapter.path
            except Exception as e:
                print(f"[BLE] Standard adapter lookup failed: {e}")
                print("[BLE] Trying direct adapter path...")
                # Fallback: create adapter directly with known path
                introspection = await self.bus.introspect("org.bluez", adapter_path)
                proxy = self.bus.get_proxy_object("org.bluez", adapter_path, introspection)
                self.adapter = Adapter(proxy)

            print(f"[BLE] Using adapter: {adapter_path}")

            # Configure adapter for multiple connections WITHOUT bonding/pairing
            # Get the adapter properties interface
            try:
                adapter_props = self.adapter._adapter_interface

                # Enable discoverable mode persistently (even when connected)
                await adapter_props.set_discoverable(True)
                await adapter_props.set_discoverable_timeout(0)  # Never timeout

                # Disable pairable mode to prevent bonding (no pairing required)
                # This ensures Samsung S23 and other devices don't force pairing dialogs
                try:
                    await adapter_props.set_pairable(False)
                    print("[BLE] Pairable mode disabled (no bonding required)")
                except Exception:
                    pass  # Some systems might not support this

                print("[BLE] Adapter configured for persistent discoverability")
            except Exception as e:
                print(f"[BLE] Warning: Could not set adapter properties: {e}")

            # Create and register service
            self.service = StressBallService()
            await self.service.register(self.bus, adapter=self.adapter)
            print(f"[BLE] Registered service: {SERVICE_UUID}")

            # Create advertisement with connectable=True to allow multiple connections
            # Advertisement(localName, serviceUUIDs, appearance, timeout)
            self.advert = Advertisement(
                localName=BLE_DEVICE_NAME,
                serviceUUIDs=[SERVICE_UUID],
                appearance=0x0340,  # Generic Sensor (BLE standard)
                timeout=0,  # Advertise indefinitely
            )

            await self.advert.register(self.bus, self.adapter)
            print(f"[BLE] Advertising as '{BLE_DEVICE_NAME}' (multi-connection enabled)")

            # Register agent for pairing (NoIoAgent = no PIN required)
            self.agent = NoIoAgent()
            await self.agent.register(self.bus)
            print("[BLE] Agent registered (no PIN required)")

            self.is_running = True

            # Start advertising monitor to keep advertising active for multiple connections
            asyncio.create_task(self._monitor_advertising())

            print("[BLE] Server started successfully!")
            print(f"[BLE] Service UUID: {SERVICE_UUID}")
            print(f"[BLE] Settings Char: {CHAR_SETTINGS_UUID}")
            print(f"[BLE] Command Char: {CHAR_COMMAND_UUID}")
            print(f"[BLE] Status Char: {CHAR_STATUS_UUID}")
            print(f"[BLE] Sensor Char: {CHAR_SENSOR_UUID}")
            print(f"[BLE] Emotion Char: {CHAR_EMOTION_UUID}")
            print("[BLE] Multi-connection support: ENABLED")
            return True

        except Exception as e:
            print(f"[BLE] Failed to start: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def _monitor_advertising(self):
        """Monitor and maintain advertising status for multiple connections.

        This keeps the device discoverable even when clients are connected,
        allowing additional phones to discover and connect.
        """
        print("[BLE] Advertising monitor started")
        check_interval = 10  # Check every 10 seconds

        while self.is_running:
            try:
                await asyncio.sleep(check_interval)

                if not self.is_running:
                    break

                # Check if adapter is still discoverable
                try:
                    adapter_props = self.adapter._adapter_interface
                    is_discoverable = await adapter_props.get_discoverable()

                    if not is_discoverable:
                        print("[BLE] Advertising lost, re-enabling...")
                        await adapter_props.set_discoverable(True)
                        print("[BLE] Advertising restored")
                except Exception as e:
                    # Silently continue if we can't check/restore
                    pass

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[BLE] Advertising monitor error: {e}")
                await asyncio.sleep(check_interval)

        print("[BLE] Advertising monitor stopped")

    async def stop(self):
        """Stop the BLE server."""
        try:
            # Advertisement uses Release() not unregister
            if self.advert:
                try:
                    self.advert.Release()
                except Exception:
                    pass  # Release might fail if already released

            # Service unregistration
            if self.service:
                try:
                    await self.service.unregister(self.bus)
                except Exception:
                    pass

            self.is_running = False
            print("[BLE] Server stopped")
        except Exception as e:
            print(f"[BLE] Error stopping: {e}")


# ======================
# Factory function
# ======================

def create_ble_service() -> BLEService:
    """Create BLE service."""
    return BLEService()


# ======================
# Test / Standalone run
# ======================

async def main():
    """Test the BLE service."""
    print("=" * 50)
    print("BLE Service Test (bluez-peripheral)")
    print("=" * 50)

    if not BLUEZ_AVAILABLE:
        print("\nERROR: bluez-peripheral not available!")
        print("Install with: pip install bluez-peripheral")
        return

    service = BLEService()
    success = await service.start()

    if not success:
        print("\nFailed to start BLE service")
        return

    print("\n" + "=" * 50)
    print("BLE Commands available from mobile app:")
    print("=" * 50)
    print(f"  CMD_SET_ANIMATION (0x01): Set animation 1-5")
    print(f"  CMD_SET_SOUND (0x02): Set sound 1-13 (for distress response)")
    print(f"  CMD_FIND_DEVICE (0x03): Play alarm (sound 14)")
    print(f"  CMD_ENABLE_ANIMATION (0x04): Enable/disable animation")
    print(f"  CMD_ENABLE_SOUND (0x05): Enable/disable sound")
    print(f"  CMD_STOP_SOUND (0x06): Stop current sound")
    print(f"  CMD_PLAY_SOUND (0x08): Play specific sound on ESP32")
    print(f"  CMD_PLAY_ANIMATION (0x09): Play animation 1-5 on TFT immediately")
    print("=" * 50)

    print("\nServer running. Press Ctrl+C to stop...")

    try:
        # Keep running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        await service.stop()


if __name__ == "__main__":
    asyncio.run(main())
