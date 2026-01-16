"""
Noise Monitor Service - Monitors environmental noise via INMP441 I2S microphone
"""

import asyncio
import alsaaudio
import numpy as np
from config.settings import (
    NOISE_MONITOR_DEVICE,
    NOISE_MONITOR_SAMPLE_RATE,
    NOISE_MONITOR_CHANNELS,
    NOISE_MONITOR_PERIOD_SIZE,
    NOISE_MONITOR_READ_INTERVAL,
    NOISE_MONITOR_ALERT_THRESHOLD,
    NOISE_MONITOR_SMOOTHING_WINDOW,
    NOISE_MONITOR_CALIBRATION_OFFSET,
)


class NoiseMonitorService:
    """Monitors ambient noise level using I2S microphone"""

    def __init__(self):
        self.is_running = False
        self.pcm = None  # ALSA PCM device

        # Current readings
        self.current_db_level = 0.0
        self.current_category = "quiet"

        # Smoothing buffer for moving average
        self._db_buffer = []
        self._smoothing_window = NOISE_MONITOR_SMOOTHING_WINDOW

        # Callbacks
        self._on_reading_callback = None
        self._on_high_noise_callback = None

        # Configuration
        self.device = NOISE_MONITOR_DEVICE
        self.sample_rate = NOISE_MONITOR_SAMPLE_RATE
        self.channels = NOISE_MONITOR_CHANNELS
        self.period_size = NOISE_MONITOR_PERIOD_SIZE
        self.alert_threshold = NOISE_MONITOR_ALERT_THRESHOLD
        self.read_interval = NOISE_MONITOR_READ_INTERVAL
        self.calibration_offset = NOISE_MONITOR_CALIBRATION_OFFSET

        print(f"[NoiseMonitor] Initialized (device: {self.device}, threshold: {self.alert_threshold} dB)")

    async def start(self) -> bool:
        """Initialize I2S microphone and start monitoring"""
        try:
            print(f"[NoiseMonitor] Starting on device {self.device}...")

            # Initialize ALSA PCM device
            self.pcm = alsaaudio.PCM(
                type=alsaaudio.PCM_CAPTURE,
                mode=alsaaudio.PCM_NORMAL,
                device=self.device
            )

            # Configure audio format for INMP441 I2S microphone
            self.pcm.setchannels(self.channels)  # Stereo (I2S requirement)
            self.pcm.setrate(self.sample_rate)
            self.pcm.setformat(alsaaudio.PCM_FORMAT_S32_LE)  # 32-bit signed
            self.pcm.setperiodsize(self.period_size)

            self.is_running = True
            asyncio.create_task(self._read_loop())

            print(f"[NoiseMonitor] Started successfully (rate: {self.sample_rate}Hz, channels: {self.channels})")
            return True

        except alsaaudio.ALSAAudioError as e:
            print(f"[NoiseMonitor] ALSA error: {e}")
            return False
        except Exception as e:
            print(f"[NoiseMonitor] Failed to start: {e}")
            return False

    async def stop(self):
        """Stop monitoring and cleanup resources"""
        print("[NoiseMonitor] Stopping...")
        self.is_running = False

        if self.pcm:
            try:
                self.pcm.close()
                print("[NoiseMonitor] ALSA device closed")
            except Exception as e:
                print(f"[NoiseMonitor] Cleanup error: {e}")

        # Clear buffer
        self._db_buffer.clear()

    async def _read_loop(self):
        """Continuous audio reading loop"""
        consecutive_errors = 0
        max_errors = 5

        print("[NoiseMonitor] Read loop started")

        while self.is_running:
            try:
                # Read audio chunk (blocking call - run in executor to avoid blocking event loop)
                loop = asyncio.get_event_loop()
                length, data = await loop.run_in_executor(None, self.pcm.read)

                # Debug: Log read status
                if consecutive_errors == 0 and not hasattr(self, '_first_read_logged'):
                    print(f"[NoiseMonitor] DEBUG: First read - length={length}, data_size={len(data) if data else 0}")
                    self._first_read_logged = True

                if length > 0:
                    # Calculate dB level
                    db_level = self._calculate_db_level(data)

                    # Apply smoothing
                    smoothed_db = self._smooth_db_reading(db_level)

                    # Categorize
                    category = self._categorize_noise(smoothed_db)

                    # Update state
                    self.current_db_level = smoothed_db
                    self.current_category = category

                    # Create reading data
                    reading = {
                        "db_level": smoothed_db,
                        "category": category,
                        "raw_db": db_level,
                    }

                    # Debug logging (comment out after testing)
                    print(f"[NoiseMonitor] {smoothed_db:.1f} dB ({category})")

                    # Notify callbacks
                    if self._on_reading_callback:
                        self._on_reading_callback(reading)

                    # Check for high noise alert
                    if smoothed_db >= self.alert_threshold:
                        if self._on_high_noise_callback:
                            self._on_high_noise_callback(reading)

                    # Reset error counter on success
                    consecutive_errors = 0

                # Wait before next reading
                await asyncio.sleep(self.read_interval)

            except alsaaudio.ALSAAudioError as e:
                consecutive_errors += 1
                if consecutive_errors <= max_errors:
                    print(f"[NoiseMonitor] ALSA read error ({consecutive_errors}/{max_errors}): {e}")
                else:
                    print(f"[NoiseMonitor] Too many consecutive errors, stopping...")
                    self.is_running = False
                await asyncio.sleep(1)

            except Exception as e:
                consecutive_errors += 1
                print(f"[NoiseMonitor] Read error ({consecutive_errors}/{max_errors}): {e}")
                if consecutive_errors > max_errors:
                    self.is_running = False
                await asyncio.sleep(1)

    def _calculate_db_level(self, audio_data: bytes) -> float:
        """Calculate dB level from raw PCM audio data"""
        try:
            # Convert bytes to numpy array (S32_LE format)
            # Each sample is 4 bytes (32-bit signed little-endian)
            samples = np.frombuffer(audio_data, dtype=np.int32)

            if len(samples) == 0:
                return 0.0

            # Use only left channel (every other sample for stereo)
            left_channel = samples[::2]

            if len(left_channel) == 0:
                return 0.0

            # Normalize to float range [-1.0, 1.0]
            # For 32-bit signed: max value is 2^31 - 1
            normalized = left_channel.astype(np.float64) / (2**31)

            # Calculate RMS (Root Mean Square)
            rms = np.sqrt(np.mean(normalized**2))

            # Debug: Check if we're getting audio data
            max_val = np.max(np.abs(normalized))
            if max_val > 0.001:  # Only log when there's actual audio
                print(f"[NoiseMonitor] DEBUG: samples={len(samples)}, max_amplitude={max_val:.6f}, rms={rms:.10f}")

            # Avoid log(0) error
            if rms < 1e-10:
                return 0.0

            # Convert to dB SPL (Sound Pressure Level)
            # For environmental noise monitoring, we need to map digital amplitude to SPL
            # Typical calibration: full scale (1.0) = ~94 dB SPL (standard reference)
            # Formula: dB_SPL = 20 * log10(rms) + reference_level
            # Using 94 dB as the reference for digital full-scale
            db = 20 * np.log10(rms) + 94.0

            # Apply calibration offset (for fine-tuning in the field)
            db += self.calibration_offset

            # Clamp to reasonable range (0-120 dB SPL)
            return max(0.0, min(120.0, db))

        except Exception as e:
            print(f"[NoiseMonitor] dB calculation error: {e}")
            return 0.0

    def _categorize_noise(self, db_level: float) -> str:
        """Categorize noise level into predefined categories"""
        if db_level < 40:
            return "silent"
        elif db_level < 55:
            return "quiet"
        elif db_level < 70:
            return "moderate"
        elif db_level < 85:
            return "loud"
        else:
            return "very_loud"

    def _smooth_db_reading(self, db_level: float) -> float:
        """Apply moving average smoothing to reduce jitter"""
        self._db_buffer.append(db_level)

        # Keep buffer size limited
        if len(self._db_buffer) > self._smoothing_window:
            self._db_buffer.pop(0)

        # Return average
        return sum(self._db_buffer) / len(self._db_buffer)

    def on_reading(self, callback):
        """Register callback for noise readings

        Callback signature: callback(reading: dict)
        Reading dict contains: {"db_level": float, "category": str, "raw_db": float}
        """
        self._on_reading_callback = callback

    def on_high_noise_alert(self, callback):
        """Register callback for high noise alerts (>threshold)

        Callback signature: callback(reading: dict)
        Reading dict contains: {"db_level": float, "category": str, "raw_db": float}
        """
        self._on_high_noise_callback = callback

    def get_current_reading(self) -> dict:
        """Get the most recent noise reading"""
        return {
            "db_level": self.current_db_level,
            "category": self.current_category,
        }

    def get_status(self) -> dict:
        """Get noise monitor service status"""
        return {
            "is_running": self.is_running,
            "device": self.device,
            "sample_rate": self.sample_rate,
            "alert_threshold": self.alert_threshold,
            "last_reading": self.get_current_reading(),
        }
