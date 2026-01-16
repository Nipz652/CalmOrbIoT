#!/usr/bin/env python3
"""
BLE Beacon Service - Scans for ESP32 BLE beacon to determine proximity

This service runs as a BLE scanner (central role) to detect the ESP32's
BLE beacon advertisement. It measures RSSI to determine if the child
is NEAR, MEDIUM, FAR, or OUT_OF_RANGE.

Note: This runs separately from the BLE GATT server (ble_service.py) which
acts as a peripheral for mobile app communication. Both can run concurrently.
"""

import asyncio
from typing import Callable, Optional, List
from dataclasses import dataclass
from enum import Enum
from collections import deque
import time
import statistics

# Try to import bleak for BLE scanning
try:
    from bleak import BleakScanner
    from bleak.backends.device import BLEDevice
    from bleak.backends.scanner import AdvertisementData
    BLEAK_AVAILABLE = True
except ImportError:
    BLEAK_AVAILABLE = False
    print("[BLE Beacon] Warning: 'bleak' library not installed. Run: pip install bleak")


# ======================
# Proximity Zone Enum
# ======================

class ProximityZone(Enum):
    """Proximity zones based on BLE RSSI signal strength."""
    NEAR = "NEAR"              # < 15 meters (RSSI > -99 dBm)
    MEDIUM = "MEDIUM"          # 15-25 meters (RSSI -99 to -105 dBm)
    FAR = "FAR"                # 25-35 meters (RSSI -105 to -110 dBm)
    OUT_OF_RANGE = "OUT_OF_RANGE"  # > 35 meters or not detected (RSSI < -110 dBm)
    UNKNOWN = "UNKNOWN"        # Not yet detected


# ======================
# Configuration
# ======================

@dataclass
class BeaconConfig:
    """Configuration for BLE beacon scanning."""
    # ESP32 beacon identification
    device_name: str = "ESP32-StressBall"

    # RSSI calibration - measured RSSI at 1 meter distance
    # Calibrate this value for your environment (typically -55 to -70 dBm)
    tx_power_at_1m: int = -70

    # RSSI thresholds for zones (in dBm, more negative = weaker signal)
    # Updated for container environment - increased range
    rssi_near: int = -99        # Stronger than -99 dBm = NEAR (< 15m)
    rssi_medium: int = -105     # -99 to -105 dBm = MEDIUM (15-25m)
    rssi_far: int = -110        # -105 to -110 dBm = FAR (25-35m)
                                # Weaker than -110 dBm = OUT_OF_RANGE (> 35m)

    # Scanning parameters (optimized for catching intermittent beacons)
    scan_interval: float = 0.1          # Seconds between scans (minimal gap for fast cycles)
    scan_duration: float = 3.0          # Duration of each scan (balanced coverage)

    # RSSI smoothing (reduces noise)
    rssi_samples: int = 8               # Number of samples to average (good smoothing)

    # Lost device detection (tolerant of missed scans)
    lost_timeout: float = 25.0          # Seconds before marking as OUT_OF_RANGE

    # Zone change debounce (prevents rapid zone flickering)
    zone_change_threshold: int = 3      # Consecutive readings needed to change zone (balanced)


# ======================
# Beacon Data
# ======================

@dataclass
class BeaconData:
    """Current state of the detected beacon."""
    detected: bool = False
    rssi: int = 0
    rssi_smoothed: float = 0.0
    distance_meters: float = -1.0
    zone: ProximityZone = ProximityZone.UNKNOWN
    last_seen: float = 0.0
    device_name: str = ""
    device_address: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "detected": self.detected,
            "rssi": self.rssi,
            "rssi_smoothed": round(self.rssi_smoothed, 1),
            "distance_meters": round(self.distance_meters, 2),
            "zone": self.zone.value,
            "last_seen_ago": round(time.time() - self.last_seen, 1) if self.last_seen > 0 else -1,
            "device_name": self.device_name,
            "device_address": self.device_address,
        }


# ======================
# BLE Beacon Service
# ======================

class BLEBeaconService:
    """
    Service for scanning and tracking ESP32 BLE beacon proximity.

    Usage:
        beacon_service = BLEBeaconService()
        beacon_service.on_zone_change = my_callback_function
        await beacon_service.start()

        # Get current state
        data = beacon_service.get_beacon_data()
        zone = beacon_service.get_zone()
    """

    def __init__(self, config: Optional[BeaconConfig] = None):
        """Initialize the beacon service."""
        self.config = config or BeaconConfig()
        self._beacon_data = BeaconData()
        self._rssi_history: deque = deque(maxlen=self.config.rssi_samples)
        self._zone_counter: dict = {zone: 0 for zone in ProximityZone}
        self._is_running = False
        self._scan_task: Optional[asyncio.Task] = None

        # Callbacks
        self._on_zone_change: Optional[Callable[[ProximityZone, ProximityZone], None]] = None
        self._on_beacon_detected: Optional[Callable[[BeaconData], None]] = None
        self._on_beacon_lost: Optional[Callable[[], None]] = None

    # ======================
    # Properties
    # ======================

    @property
    def on_zone_change(self) -> Optional[Callable]:
        """Callback when proximity zone changes."""
        return self._on_zone_change

    @on_zone_change.setter
    def on_zone_change(self, callback: Callable[[ProximityZone, ProximityZone], None]):
        """Set callback for zone changes. Args: (old_zone, new_zone)"""
        self._on_zone_change = callback

    @property
    def on_beacon_detected(self) -> Optional[Callable]:
        """Callback when beacon is first detected."""
        return self._on_beacon_detected

    @on_beacon_detected.setter
    def on_beacon_detected(self, callback: Callable[[BeaconData], None]):
        self._on_beacon_detected = callback

    @property
    def on_beacon_lost(self) -> Optional[Callable]:
        """Callback when beacon is lost."""
        return self._on_beacon_lost

    @on_beacon_lost.setter
    def on_beacon_lost(self, callback: Callable[[], None]):
        self._on_beacon_lost = callback

    @property
    def is_running(self) -> bool:
        """Check if the service is running."""
        return self._is_running

    # ======================
    # Public Methods
    # ======================

    async def start(self) -> bool:
        """Start the beacon scanning service."""
        if not BLEAK_AVAILABLE:
            print("[BLE Beacon] Cannot start - 'bleak' library not available")
            return False

        if self._is_running:
            print("[BLE Beacon] Service already running")
            return True

        print(f"[BLE Beacon] Starting scanner for '{self.config.device_name}'...")
        print(f"[BLE Beacon] TX Power at 1m: {self.config.tx_power_at_1m} dBm")
        print(f"[BLE Beacon] Zone thresholds - NEAR: >{self.config.rssi_near}, "
              f"MEDIUM: {self.config.rssi_near} to {self.config.rssi_medium}, "
              f"FAR: {self.config.rssi_medium} to {self.config.rssi_far}")

        self._is_running = True
        self._scan_task = asyncio.create_task(self._scan_loop())

        print("[BLE Beacon] Scanner started")
        return True

    async def stop(self):
        """Stop the beacon scanning service."""
        if not self._is_running:
            return

        self._is_running = False

        if self._scan_task:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass
            self._scan_task = None

        print("[BLE Beacon] Scanner stopped")

    def get_beacon_data(self) -> BeaconData:
        """Get current beacon data."""
        return self._beacon_data

    def get_zone(self) -> ProximityZone:
        """Get current proximity zone."""
        return self._beacon_data.zone

    def get_distance(self) -> float:
        """Get estimated distance in meters (-1 if unknown)."""
        return self._beacon_data.distance_meters

    def is_detected(self) -> bool:
        """Check if beacon is currently detected."""
        return self._beacon_data.detected

    def calibrate_tx_power(self, rssi_at_1m: int):
        """
        Calibrate the TX power for better distance estimation.

        To calibrate:
        1. Place ESP32 exactly 1 meter from Raspberry Pi
        2. Run this service and note the average RSSI
        3. Call this method with that value
        """
        self.config.tx_power_at_1m = rssi_at_1m
        print(f"[BLE Beacon] TX Power calibrated to {rssi_at_1m} dBm at 1 meter")

    # ======================
    # Distance Calculation
    # ======================

    def _rssi_to_distance(self, rssi: float) -> float:
        """
        Estimate distance from RSSI using log-distance path loss model.

        This is an approximation - BLE RSSI is affected by:
        - Walls and obstacles
        - Human body blocking
        - Interference from other devices
        - Antenna orientation

        Best used for zone detection (near/far), not precise positioning.
        """
        if rssi == 0:
            return -1.0

        # Path loss exponent (n) - typically 2-4 for indoor environments
        # Lower = less obstruction, Higher = more walls/obstacles
        n = 2.5

        # Log-distance path loss model
        # distance = 10 ^ ((TxPower - RSSI) / (10 * n))
        ratio = (self.config.tx_power_at_1m - rssi) / (10 * n)
        distance = pow(10, ratio)

        return distance

    def _get_zone_from_rssi(self, rssi: float) -> ProximityZone:
        """Determine proximity zone from RSSI value."""
        if rssi > self.config.rssi_near:
            return ProximityZone.NEAR
        elif rssi > self.config.rssi_medium:
            return ProximityZone.MEDIUM
        elif rssi > self.config.rssi_far:
            return ProximityZone.FAR
        else:
            return ProximityZone.OUT_OF_RANGE

    def _smooth_rssi(self, rssi: int) -> float:
        self._rssi_history.append(rssi)
        return statistics.median(self._rssi_history)

    # ======================
    # Zone Change Detection
    # ======================

    def _update_zone_with_debounce(self, new_zone: ProximityZone):
        """
        Update zone with debouncing to prevent rapid flickering.

        Requires multiple consecutive readings in the same zone
        before changing the reported zone.
        """
        old_zone = self._beacon_data.zone

        # Reset counter for other zones, increment for this zone
        for zone in ProximityZone:
            if zone == new_zone:
                self._zone_counter[zone] = min(
                    self._zone_counter[zone] + 1,
                    self.config.zone_change_threshold + 1
                )
            else:
                self._zone_counter[zone] = 0

        # Check if we should change zone
        if self._zone_counter[new_zone] >= self.config.zone_change_threshold:
            if new_zone != old_zone:
                self._beacon_data.zone = new_zone
                print(f"[BLE Beacon] Zone changed: {old_zone.value} -> {new_zone.value}")

                # Fire callback
                if self._on_zone_change:
                    try:
                        self._on_zone_change(old_zone, new_zone)
                    except Exception as e:
                        print(f"[BLE Beacon] Zone change callback error: {e}")

    # ======================
    # Scanning
    # ======================

    async def _scan_loop(self):
        """
        Main scanning loop.

        Timing pattern:
        - Scan for scan_duration (3s)
        - Sleep for scan_interval (0.1s)
        - Repeat (new scan every 3.1 seconds)

        This creates high scan coverage (3s scan / 3.1s total = 97% coverage)
        with frequent scan starts to catch intermittent BLE advertisements
        and reduce false "lost" detections.
        """
        while self._is_running:
            try:
                await self._perform_scan()
                await asyncio.sleep(self.config.scan_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[BLE Beacon] Scan error: {e}")
                await asyncio.sleep(self.config.scan_interval)

    async def _perform_scan(self):
        """Perform a single BLE scan."""
        esp32_found = False

        try:
            # Scan for devices
            devices = await BleakScanner.discover(
                timeout=self.config.scan_duration,
                return_adv=True
            )

            # Look for our ESP32
            for device, adv_data in devices.values():
                if self._is_target_device(device, adv_data):
                    esp32_found = True
                    await self._process_detection(device, adv_data)
                    break

        except Exception as e:
            import traceback
            print(f"[BLE Beacon] Scan error: {e}")
            traceback.print_exc()

        # Handle lost device
        if not esp32_found:
            self._handle_no_detection()

    def _is_target_device(self, device, adv_data) -> bool:
        """
        Check if this advertisement belongs to our ESP32 beacon.
        """
        # 1. Match by device name
        if adv_data and adv_data.local_name:
            if self.config.device_name in adv_data.local_name:
                return True
        if device.name and self.config.device_name in device.name:
            return True

        return False

    async def _process_detection(self, device: 'BLEDevice', adv_data: 'AdvertisementData'):
        """Process a detected ESP32 beacon."""
        was_detected = self._beacon_data.detected

        # Get RSSI from AdvertisementData (newer bleak versions)
        rssi = -100
        if adv_data and hasattr(adv_data, 'rssi') and adv_data.rssi is not None:
            rssi = adv_data.rssi
        elif hasattr(device, 'rssi') and device.rssi is not None:
            rssi = device.rssi

        # Smooth RSSI
        rssi_smoothed = self._smooth_rssi(rssi)

        # Calculate distance
        distance = self._rssi_to_distance(rssi_smoothed)

        # Determine zone
        new_zone = self._get_zone_from_rssi(rssi_smoothed)

        # Update beacon data
        self._beacon_data.detected = True
        self._beacon_data.rssi = rssi
        self._beacon_data.rssi_smoothed = rssi_smoothed
        self._beacon_data.distance_meters = distance
        self._beacon_data.last_seen = time.time()
        self._beacon_data.device_name = device.name or ""
        self._beacon_data.device_address = device.address

        # Update zone with debouncing
        self._update_zone_with_debounce(new_zone)

        # Print status
        print(f"[BLE Beacon] {device.name} | RSSI: {rssi} dBm (avg: {rssi_smoothed:.1f}) | "
              f"Distance: ~{distance:.1f}m | Zone: {self._beacon_data.zone.value}")

        # Fire callback if first detection
        if not was_detected and self._on_beacon_detected:
            try:
                self._on_beacon_detected(self._beacon_data)
            except Exception as e:
                print(f"[BLE Beacon] Detection callback error: {e}")

    def _handle_no_detection(self):
        """Handle case when ESP32 is not detected."""
        if not self._beacon_data.detected:
            return  # Already marked as not detected

        # Check timeout
        time_since_seen = time.time() - self._beacon_data.last_seen

        if time_since_seen > self.config.lost_timeout:
            was_detected = self._beacon_data.detected

            self._beacon_data.detected = False
            self._beacon_data.rssi = 0
            self._rssi_history.clear()

            # Update zone
            old_zone = self._beacon_data.zone
            self._beacon_data.zone = ProximityZone.OUT_OF_RANGE

            print(f"[BLE Beacon] Device lost - not seen for {time_since_seen:.1f}s")

            # Fire callbacks
            if was_detected and self._on_beacon_lost:
                try:
                    self._on_beacon_lost()
                except Exception as e:
                    print(f"[BLE Beacon] Lost callback error: {e}")

            if old_zone != ProximityZone.OUT_OF_RANGE and self._on_zone_change:
                try:
                    self._on_zone_change(old_zone, ProximityZone.OUT_OF_RANGE)
                except Exception as e:
                    print(f"[BLE Beacon] Zone change callback error: {e}")
        else:
            print(f"[BLE Beacon] Device not in scan, last seen {time_since_seen:.1f}s ago")


# ======================
# Convenience Functions
# ======================

def create_beacon_service(
    device_name: str = "ESP32-StressBall",
    tx_power: int = -59
) -> BLEBeaconService:
    """Create a beacon service with custom configuration."""
    config = BeaconConfig(
        device_name=device_name,
        tx_power_at_1m=tx_power
    )
    return BLEBeaconService(config)


# ======================
# Test / Standalone Run
# ======================

async def main():
    """Test the beacon service."""
    print("=" * 60)
    print("BLE Beacon Scanner Service Test")
    print("=" * 60)
    print()

    if not BLEAK_AVAILABLE:
        print("ERROR: 'bleak' library not available")
        print("Install with: pip install bleak")
        return

    # Create service with default config
    service = BLEBeaconService()

    # Set up callbacks
    def on_zone_changed(old_zone: ProximityZone, new_zone: ProximityZone):
        print(f"\n{'='*40}")
        print(f"ZONE CHANGED: {old_zone.value} -> {new_zone.value}")
        if new_zone == ProximityZone.OUT_OF_RANGE:
            print("WARNING: Child is beyond 35m or not detected!")
        elif new_zone == ProximityZone.FAR:
            print("NOTICE: Child is 25-35m away")
        elif new_zone == ProximityZone.MEDIUM:
            print("INFO: Child is 15-25m away")
        elif new_zone == ProximityZone.NEAR:
            print("OK: Child is within 15m")
        print(f"{'='*40}\n")

    def on_beacon_detected(data: BeaconData):
        print(f"\n[DETECTED] ESP32 found at {data.device_address}")

    def on_beacon_lost():
        print(f"\n[LOST] ESP32 beacon lost - child may have left range!")

    service.on_zone_change = on_zone_changed
    service.on_beacon_detected = on_beacon_detected
    service.on_beacon_lost = on_beacon_lost

    # Start scanning
    await service.start()

    print("\nProximity Zones:")
    print(f"  NEAR:         > {service.config.rssi_near} dBm (< 15m)")
    print(f"  MEDIUM:       {service.config.rssi_near} to {service.config.rssi_medium} dBm (15-25m)")
    print(f"  FAR:          {service.config.rssi_medium} to {service.config.rssi_far} dBm (25-35m)")
    print(f"  OUT_OF_RANGE: < {service.config.rssi_far} dBm (> 35m)")
    print()
    print("Press Ctrl+C to stop...\n")

    try:
        while True:
            await asyncio.sleep(5)

            # Print current status periodically
            data = service.get_beacon_data()
            if data.detected:
                print(f"[STATUS] Zone: {data.zone.value} | "
                      f"Distance: ~{data.distance_meters:.1f}m | "
                      f"RSSI: {data.rssi_smoothed:.1f} dBm")
            else:
                print(f"[STATUS] ESP32 not detected")

    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        await service.stop()


if __name__ == "__main__":
    asyncio.run(main())
