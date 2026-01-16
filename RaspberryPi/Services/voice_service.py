"""
Voice Service - Voice command recognition using Atom Echo

Implements wake word detection ("ORB!") and command recognition
for MUSIC, ANIME, and BOTH commands using:
- Atom Echo for audio input/output via USB serial
- Voice Activity Detection (VAD) to filter noise
- Vosk for offline speech recognition
- pyttsx3 for TTS responses

State Machine:
IDLE -> (wake word) -> READY -> (command/timeout) -> IDLE
"""

import asyncio
import logging
import time
import json
import os
import struct
import queue
from enum import Enum
from typing import Optional, Callable

# Import configuration
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

logger = logging.getLogger(__name__)


class VoiceState(Enum):
    """Voice command state machine states."""
    IDLE = "idle"              # Listening for wake word
    READY = "ready"            # Wake word detected, waiting for command
    PROCESSING = "processing"  # Processing command


class VoiceService:
    """
    Voice command service using Atom Echo.

    Handles:
    - USB serial communication with Atom Echo
    - Voice Activity Detection (VAD) to filter noise
    - Wake word detection ("ORB")
    - Command recognition (MUSIC, ANIME, BOTH)
    - TTS responses via Atom Echo speaker
    """

    def __init__(self):
        self.is_running = False
        self.state = VoiceState.IDLE
        self._state_start_time = 0

        # Serial connection (for TTS output to Atom Echo)
        self.serial = None
        self._serial_connected = False

        # Microphone input (sounddevice)
        self._audio_stream = None
        self._audio_queue = queue.Queue()
        self._mic_connected = False

        # Audio processing
        self.vad = None
        self.recognizer = None
        self.model = None

        # TTS engine
        self.tts_engine = None

        # Callbacks
        self._on_command_callback: Optional[Callable[[str, str], None]] = None
        self._on_state_change_callback: Optional[Callable[[VoiceState], None]] = None

        # Audio buffer
        self._audio_buffer = bytearray()
        self._frame_size = settings.VOICE_FRAME_SIZE * 2  # 2 bytes per sample (16-bit)

        # Dependencies available flags
        self._serial_available = False
        self._sounddevice_available = False
        self._vad_available = False
        self._vosk_available = False
        self._tts_available = False

        # Check and import dependencies
        self._check_dependencies()

    def _check_dependencies(self):
        """Check and import optional dependencies."""
        # Check pyserial (for TTS output)
        try:
            import serial
            self._serial_available = True
            logger.info("[Voice] pyserial available (for TTS output)")
        except ImportError:
            logger.warning("[Voice] pyserial not installed - TTS to Atom Echo disabled")

        # Check sounddevice (for microphone input)
        try:
            import sounddevice as sd
            self._sounddevice_available = True
            logger.info("[Voice] sounddevice available (for microphone input)")
        except ImportError:
            logger.warning("[Voice] sounddevice not installed - microphone input disabled")

        # Check webrtcvad
        try:
            import webrtcvad
            self._vad_available = True
            logger.info("[Voice] webrtcvad available")
        except ImportError:
            logger.warning("[Voice] webrtcvad not installed - VAD disabled")

        # Check vosk
        try:
            from vosk import Model, KaldiRecognizer
            self._vosk_available = True
            logger.info("[Voice] vosk available")
        except ImportError:
            logger.warning("[Voice] vosk not installed - speech recognition disabled")

        # Check pyttsx3
        try:
            import pyttsx3
            self._tts_available = True
            logger.info("[Voice] pyttsx3 available")
        except ImportError:
            logger.warning("[Voice] pyttsx3 not installed - TTS disabled")

    async def start(self) -> bool:
        """
        Initialize and start the voice service.

        Returns:
            bool: True if started successfully
        """
        if self.is_running:
            logger.warning("[Voice] Service already running")
            return True

        logger.info("[Voice] Starting voice service...")

        try:
            # Initialize audio input based on configured type
            input_type = getattr(settings, 'VOICE_INPUT_TYPE', 'sounddevice')

            if input_type == 'serial':
                # Use Atom Echo I2S microphone via serial
                if not self._init_serial():
                    logger.error("[Voice] Serial connection failed - voice commands disabled")
                    return False
                self._mic_connected = True  # Serial audio streaming is the mic
                logger.info("[Voice] Using Atom Echo I2S microphone via serial")
            else:
                # Use sounddevice (webcam/USB mic)
                if not self._init_microphone():
                    logger.error("[Voice] Microphone initialization failed - voice commands disabled")
                    return False
                # Serial still needed for TTS output to Atom Echo (optional)
                if not self._init_serial():
                    logger.warning("[Voice] Serial connection failed - TTS to Atom Echo disabled")

            if not self._init_vad():
                logger.warning("[Voice] VAD initialization failed - continuing without noise filter")

            if not self._init_vosk():
                logger.error("[Voice] Vosk initialization failed - voice commands disabled")
                return False

            if not self._init_tts():
                logger.warning("[Voice] TTS initialization failed - continuing without audio responses")

            self.is_running = True
            self.state = VoiceState.IDLE
            self._state_start_time = time.time()

            logger.info("[Voice] Voice service started successfully")
            logger.info(f"[Voice] Wake word: '{settings.VOICE_WAKE_WORD}'")
            logger.info(f"[Voice] Commands: {list(settings.VOICE_COMMANDS.keys())}")

            return True

        except Exception as e:
            logger.error(f"[Voice] Failed to start: {e}")
            return False

    async def stop(self):
        """Stop the voice service and cleanup resources."""
        logger.info("[Voice] Stopping voice service...")
        self.is_running = False

        # Close audio stream
        if self._audio_stream:
            try:
                self._audio_stream.stop()
                self._audio_stream.close()
                logger.info("[Voice] Audio stream closed")
            except Exception as e:
                logger.error(f"[Voice] Error closing audio stream: {e}")

        self._audio_stream = None
        self._mic_connected = False

        # Close serial connection (for TTS)
        if self.serial and self.serial.is_open:
            try:
                self._send_led_command(settings.VOICE_LED_OFF)
                self.serial.close()
            except Exception as e:
                logger.error(f"[Voice] Error closing serial: {e}")

        self.serial = None
        self._serial_connected = False

        logger.info("[Voice] Voice service stopped")

    def _init_microphone(self) -> bool:
        """Initialize microphone input using sounddevice."""
        if not self._sounddevice_available:
            logger.error("[Voice] sounddevice not available")
            return False

        try:
            import sounddevice as sd

            # Get configured device
            device_index = getattr(settings, 'VOICE_MIC_DEVICE', None)

            # List available devices for debugging
            devices = sd.query_devices()
            logger.info(f"[Voice] Available audio devices:")
            for i, dev in enumerate(devices):
                if dev['max_input_channels'] > 0:
                    marker = " <--" if i == device_index else ""
                    logger.info(f"[Voice]   [{i}] {dev['name']} ({dev['max_input_channels']} ch){marker}")

            # Audio callback
            def audio_callback(indata, frames, time_info, status):
                if status:
                    logger.debug(f"[Voice] Audio status: {status}")
                self._audio_queue.put(bytes(indata))

            # Create audio stream
            self._audio_stream = sd.RawInputStream(
                samplerate=settings.VOICE_SAMPLE_RATE,
                blocksize=settings.VOICE_FRAME_SIZE,
                dtype='int16',
                channels=1,
                callback=audio_callback,
                device=device_index
            )

            # Start the stream
            self._audio_stream.start()
            self._mic_connected = True

            device_name = devices[device_index]['name'] if device_index is not None else "default"
            logger.info(f"[Voice] Microphone initialized: {device_name}")
            logger.info(f"[Voice] Sample rate: {settings.VOICE_SAMPLE_RATE}Hz, Frame size: {settings.VOICE_FRAME_SIZE}")

            return True

        except Exception as e:
            logger.error(f"[Voice] Microphone initialization failed: {e}")
            return False

    def _init_serial(self) -> bool:
        """Initialize serial connection to Atom Echo (for TTS output)."""
        print(f"[DEBUG] _init_serial() called")
        print(f"[DEBUG] _serial_available = {self._serial_available}")

        if not self._serial_available:
            print("[DEBUG] Serial not available, returning False")
            return False

        try:
            import serial

            # Check if serial port exists
            print(f"[DEBUG] Checking if {settings.VOICE_SERIAL_PORT} exists")
            if not os.path.exists(settings.VOICE_SERIAL_PORT):
                logger.warning(f"[Voice] Serial port not found: {settings.VOICE_SERIAL_PORT}")
                print(f"[DEBUG] Serial port not found!")
                return False

            print(f"[DEBUG] Opening serial port {settings.VOICE_SERIAL_PORT} at {settings.VOICE_BAUD_RATE} baud")
            self.serial = serial.Serial(
                port=settings.VOICE_SERIAL_PORT,
                baudrate=settings.VOICE_BAUD_RATE,
                timeout=0.1,
                dsrdtr=False,  # Don't set DTR (prevents ESP32 reset)
                rtscts=False   # Don't use RTS/CTS flow control
            )
            print(f"[DEBUG] Serial port opened WITHOUT DTR reset")

            # Wait for Atom Echo ready signal
            logger.info(f"[Voice] Connected to {settings.VOICE_SERIAL_PORT} at {settings.VOICE_BAUD_RATE} baud")
            print(f"[DEBUG] Serial connection established!")

            # Clear any existing data in buffer
            self.serial.reset_input_buffer()
            print("[DEBUG] Buffer cleared, waiting for READY signal...")

            # Wait briefly for READY signal (with short timeout)
            # Atom Echo streams audio immediately, so READY may be missed
            start_time = time.time()
            ready_received = False
            while time.time() - start_time < 2:
                if self.serial.in_waiting > 0:
                    try:
                        data = self.serial.read(self.serial.in_waiting)
                        print(f"[DEBUG] Received data from Atom Echo: {data[:100]}")
                        if b"READY" in data:
                            logger.info("[Voice] Atom Echo ready")
                            print("[DEBUG] READY signal received!")
                            ready_received = True
                            break
                    except Exception as e:
                        print(f"[DEBUG] Exception reading serial: {e}")
                        pass
                time.sleep(0.1)

            if not ready_received:
                logger.info("[Voice] Atom Echo connected (audio stream detected)")
                print("[DEBUG] READY not received, but continuing anyway")

            self._serial_connected = True
            print(f"[DEBUG] _serial_connected = {self._serial_connected}")
            return True

        except Exception as e:
            logger.error(f"[Voice] Serial initialization failed: {e}")
            return False

    def _init_vad(self) -> bool:
        """Initialize Voice Activity Detection."""
        if not self._vad_available:
            return False

        try:
            import webrtcvad
            self.vad = webrtcvad.Vad(settings.VOICE_VAD_MODE)
            logger.info(f"[Voice] VAD initialized (mode {settings.VOICE_VAD_MODE})")
            return True
        except Exception as e:
            logger.error(f"[Voice] VAD initialization failed: {e}")
            return False

    def _init_vosk(self) -> bool:
        """Initialize Vosk speech recognition."""
        if not self._vosk_available:
            return False

        try:
            from vosk import Model, KaldiRecognizer

            model_path = settings.VOICE_MODEL_PATH

            if not os.path.exists(model_path):
                logger.error(f"[Voice] Vosk model not found: {model_path}")
                logger.error("[Voice] Download with: wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip")
                return False

            self.model = Model(model_path)

            # Use limited vocabulary if configured (dramatically improves accuracy)
            if hasattr(settings, 'VOICE_VOCABULARY') and settings.VOICE_VOCABULARY:
                grammar = json.dumps(settings.VOICE_VOCABULARY)
                self.recognizer = KaldiRecognizer(self.model, settings.VOICE_SAMPLE_RATE, grammar)
                logger.info(f"[Voice] Vosk initialized with LIMITED vocabulary ({len(settings.VOICE_VOCABULARY)} words)")
            else:
                self.recognizer = KaldiRecognizer(self.model, settings.VOICE_SAMPLE_RATE)
                logger.info(f"[Voice] Vosk initialized with OPEN vocabulary")

            logger.info(f"[Voice] Vosk model loaded from {model_path}")
            return True

        except Exception as e:
            logger.error(f"[Voice] Vosk initialization failed: {e}")
            return False

    def _init_tts(self) -> bool:
        """Initialize Text-to-Speech engine."""
        # Use espeak directly (more reliable than pyttsx3)
        import subprocess
        try:
            result = subprocess.run(['espeak', '--version'], capture_output=True, timeout=2)
            if result.returncode == 0:
                self._tts_available = True
                logger.info("[Voice] TTS engine initialized (espeak)")
                return True
            else:
                logger.error("[Voice] espeak not working")
                return False
        except Exception as e:
            logger.error(f"[Voice] TTS initialization failed: {e}")
            return False

    def _send_led_command(self, command: str):
        """Send LED command to Atom Echo."""
        if self.serial and self._serial_connected:
            try:
                self.serial.write(f"{command}\n".encode())
            except Exception as e:
                logger.error(f"[Voice] Failed to send LED command: {e}")

    def _resample_audio(self, audio_chunk: bytes, from_rate: int = 48000, to_rate: int = 16000) -> bytes:
        """
        Resample audio from one sample rate to another.

        Args:
            audio_chunk: Raw audio data (16-bit PCM)
            from_rate: Source sample rate (default: 48000 Hz)
            to_rate: Target sample rate (default: 16000 Hz)

        Returns:
            bytes: Resampled audio data
        """
        import numpy as np
        from scipy import signal

        # Convert bytes to numpy array
        audio_int16 = np.frombuffer(audio_chunk, dtype=np.int16)

        # Calculate number of output samples
        num_output_samples = int(len(audio_int16) * to_rate / from_rate)

        # Resample
        resampled = signal.resample(audio_int16, num_output_samples)

        # Convert back to int16 and bytes
        resampled_int16 = resampled.astype(np.int16)
        return resampled_int16.tobytes()

    def _is_speech(self, audio_chunk: bytes) -> bool:
        """
        Check if audio chunk contains speech using VAD.

        Args:
            audio_chunk: Raw audio data (16-bit PCM, 16kHz)

        Returns:
            bool: True if speech detected
        """
        if not self.vad:
            return True  # No VAD, assume all audio is speech

        try:
            # VAD requires specific frame sizes (10, 20, or 30 ms)
            frame_duration_ms = settings.VOICE_VAD_FRAME_MS
            frame_size = int(settings.VOICE_SAMPLE_RATE * frame_duration_ms / 1000) * 2

            if len(audio_chunk) < frame_size:
                return False

            # Check frame for speech
            return self.vad.is_speech(audio_chunk[:frame_size], settings.VOICE_SAMPLE_RATE)

        except Exception as e:
            logger.debug(f"[Voice] VAD error: {e}")
            return True

    def _recognize_text(self, audio_data: bytes) -> Optional[str]:
        """
        Recognize speech from audio data using Vosk.

        Args:
            audio_data: Raw audio data (16-bit PCM, 16kHz)

        Returns:
            str: Recognized text or None
        """
        if not self.recognizer:
            return None

        try:
            if self.recognizer.AcceptWaveform(audio_data):
                result = json.loads(self.recognizer.Result())
                text = result.get('text', '').strip()
                if text:
                    logger.debug(f"[Voice] Recognized: {text}")
                    return text
            else:
                # Partial result
                partial = json.loads(self.recognizer.PartialResult())
                partial_text = partial.get('partial', '')
                if partial_text:
                    logger.debug(f"[Voice] Partial: {partial_text}")

            return None

        except Exception as e:
            logger.error(f"[Voice] Recognition error: {e}")
            return None

    def _check_wake_word(self, text: str) -> bool:
        """Check if text contains the wake word or any of its alternatives."""
        if not text:
            return False

        text_lower = text.lower()

        # Check primary wake word
        if settings.VOICE_WAKE_WORD.lower() in text_lower:
            return True

        # Check alternatives (phonetic variations)
        if hasattr(settings, 'VOICE_WAKE_WORD_ALTERNATIVES'):
            for alt in settings.VOICE_WAKE_WORD_ALTERNATIVES:
                if alt.lower() in text_lower:
                    logger.info(f"[Voice] Wake word alternative matched: '{alt}'")
                    return True

        return False

    def _recognize_command(self, text: str) -> Optional[str]:
        """
        Check if text contains a known command.

        Args:
            text: Recognized text

        Returns:
            str: Command action or None
        """
        if not text:
            return None

        text_lower = text.lower()
        for keyword, action in settings.VOICE_COMMANDS.items():
            if keyword in text_lower:
                logger.info(f"[Voice] Command matched: '{keyword}' -> {action}")
                return action

        return None

    async def _play_tone_pattern(self, pattern_name: str):
        """
        Play a tone pattern through Atom Echo speaker.

        Tone patterns for voice command feedback (no TTS):
        - ready: 3 ascending beeps (I'm ready!)
        - play_music: 2 descending beeps
        - play_animation: 2 ascending beeps
        - play_both: 2 same volume beeps
        - error: 3 descending beeps (I'm sorry, try again)

        Args:
            pattern_name: Name of pattern (ready, play_music, play_animation, play_both, error)
        """
        if not self._serial_connected or not self.serial:
            logger.warning("[Voice] Serial not connected, skipping tone feedback")
            return

        # Map pattern names to message keywords that Atom Echo firmware understands
        pattern_messages = {
            "ready": "ready",
            "play_music": "music",
            "play_animation": "animation",
            "play_both": "both",
            "error": "sorry",
        }

        if pattern_name not in pattern_messages:
            logger.warning(f"[Voice] Unknown tone pattern: {pattern_name}")
            return

        message = pattern_messages[pattern_name]
        logger.info(f"[Voice] Playing tone pattern: {pattern_name}")
        print(f"[DEBUG VOICE] 🔊 Playing tone pattern: {pattern_name}")

        try:
            # Send single SPEAK command - Atom Echo plays the full pattern
            # Protocol: SPEAK:<message>
            command = f"SPEAK:{message}\n"

            bytes_written = self.serial.write(command.encode())
            self.serial.flush()

            print(f"[DEBUG TONE] Sent SPEAK command: {message}")
            logger.info(f"[Voice] Sent SPEAK: {message}")

            # Wait for pattern to complete (approximate timing)
            # ready: ~2-3 seconds (longer pattern with intervals)
            # others: ~1 second (2 rapid consecutive beeps)
            if pattern_name == "ready":
                await asyncio.sleep(3.0)
            else:
                await asyncio.sleep(1.0)  # Rapid beeps finish quickly

        except Exception as e:
            logger.error(f"[Voice] Tone playback error: {e}")

    async def _speak(self, text: str):
        """
        Legacy TTS method - now redirects to tone patterns.

        Kept for backward compatibility but maps text to tone patterns.
        """
        # Map legacy text responses to tone patterns
        text_lower = text.lower()

        if "ready" in text_lower or "done" in text_lower:
            await self._play_tone_pattern("ready")
        elif "music" in text_lower:
            await self._play_tone_pattern("play_music")
        elif "animation" in text_lower or "anime" in text_lower:
            await self._play_tone_pattern("play_animation")
        elif "both" in text_lower:
            await self._play_tone_pattern("play_both")
        elif "sorry" in text_lower or "again" in text_lower or "error" in text_lower:
            await self._play_tone_pattern("error")
        else:
            # Default to ready pattern
            await self._play_tone_pattern("ready")

    async def _execute_command(self, action: str):
        """
        Execute a voice command action.

        Args:
            action: Command action (play_music, play_animation, play_both)
        """
        logger.info(f"[Voice] Executing command: {action}")

        try:
            # Import distress service functions
            from services.distress_service import (
                play_sound,
                play_animation_now,
                current_sound,
                current_animation
            )

            if action == "play_music":
                print(f"[DEBUG] Voice command: play_music, calling play_sound({current_sound})")
                play_sound(current_sound)
                await self._speak("Ready!")

            elif action == "play_animation":
                play_animation_now(current_animation)
                await self._speak("Ready!")

            elif action == "play_both":
                print(f"[DEBUG] Voice command: play_both, calling play_sound({current_sound})")
                play_sound(current_sound)
                play_animation_now(current_animation)
                await self._speak("Ready!")

            # Notify callback if registered
            if self._on_command_callback:
                self._on_command_callback(action, "")

        except Exception as e:
            logger.error(f"[Voice] Command execution error: {e}")

    def _set_state(self, new_state: VoiceState):
        """Change state and update LED."""
        if new_state != self.state:
            old_state = self.state
            self.state = new_state
            self._state_start_time = time.time()

            logger.info(f"[Voice] State: {old_state.value} -> {new_state.value}")

            # Update LED
            if new_state == VoiceState.IDLE:
                self._send_led_command(settings.VOICE_LED_OFF)
            elif new_state == VoiceState.READY:
                self._send_led_command(settings.VOICE_LED_BLUE)
            elif new_state == VoiceState.PROCESSING:
                self._send_led_command(settings.VOICE_LED_GREEN)

            # Notify callback
            if self._on_state_change_callback:
                self._on_state_change_callback(new_state)

    async def listen_loop(self):
        """
        Main listening loop.

        Continuously processes audio from Atom Echo or simulated input.
        Implements state machine for wake word -> command -> execution.
        """
        logger.info("[Voice] Starting listen loop...")
        logger.info("[Voice] Say 'ORB!' to activate, then 'MUSIC', 'ANIME', or 'BOTH'")
        logger.info("[Voice] Debug: Will show when speech is detected...")

        # Track speech detection for command recognition
        speech_buffer = bytearray()
        speech_frames = 0
        silence_frames = 0
        last_speech_log = 0  # Throttle speech detection logs
        last_silence_log = 0  # Throttle silence logs
        MIN_SPEECH_FRAMES = 3  # Minimum frames to consider as speech
        MAX_SILENCE_FRAMES = 15  # Silence frames before processing
        MAX_SPEECH_FRAMES = 150  # Force processing after this many frames (~5 sec)

        while self.is_running:
            try:
                # Check for timeout in READY state
                if self.state == VoiceState.READY:
                    elapsed = time.time() - self._state_start_time
                    if elapsed >= settings.VOICE_COMMAND_TIMEOUT:
                        logger.info("[Voice] Command timeout")
                        await self._speak(settings.VOICE_RESPONSE_TIMEOUT)
                        self._set_state(VoiceState.IDLE)
                        speech_buffer.clear()
                        speech_frames = 0
                        silence_frames = 0
                        if self.recognizer:
                            self.recognizer.Reset()
                        continue

                # Read audio from microphone (serial or sounddevice)
                audio_chunk = None
                input_type = getattr(settings, 'VOICE_INPUT_TYPE', 'sounddevice')

                if self._mic_connected:
                    try:
                        if input_type == 'serial' and self.serial and self._serial_connected:
                            # Read from Atom Echo serial (blocking read with small timeout)
                            if self.serial.in_waiting >= settings.VOICE_FRAME_SIZE * 2:  # 2 bytes per sample
                                audio_chunk = self.serial.read(settings.VOICE_FRAME_SIZE * 2)
                            else:
                                await asyncio.sleep(0.01)
                                continue
                        else:
                            # Read from sounddevice queue
                            audio_chunk = self._audio_queue.get(timeout=0.1)
                    except queue.Empty:
                        # No audio available, continue waiting
                        await asyncio.sleep(0.01)
                        continue
                    except Exception as e:
                        logger.error(f"[Voice] Audio read error: {e}")
                        await asyncio.sleep(0.1)
                        continue
                else:
                    logger.warning("[Voice] Microphone not connected")
                    await asyncio.sleep(1.0)
                    continue

                if not audio_chunk:
                    await asyncio.sleep(0.03)  # ~30ms
                    continue

                # Voice Activity Detection (Atom Echo sends native 16kHz - no resampling needed)
                is_speech = self._is_speech(audio_chunk)

                import time as time_module
                current_time = time_module.time()

                if is_speech:
                    speech_frames += 1
                    silence_frames = 0
                    speech_buffer.extend(audio_chunk)

                    # Debug: Log when speech is detected (throttled)
                    if speech_frames == 1 or (current_time - last_speech_log > 2.0):
                        logger.info(f"[Voice] 🎤 Speech detected! (frames: {speech_frames})")
                        last_speech_log = current_time
                else:
                    silence_frames += 1
                    if speech_frames > 0:
                        speech_buffer.extend(audio_chunk)
                        # Debug: Log silence after speech
                        if silence_frames == 1 or (current_time - last_silence_log > 1.0):
                            logger.info(f"[Voice] 🔇 Silence... (speech: {speech_frames}, silence: {silence_frames})")
                            last_silence_log = current_time

                # Process accumulated speech after silence OR after max frames
                force_process = speech_frames >= MAX_SPEECH_FRAMES
                if (speech_frames >= MIN_SPEECH_FRAMES and silence_frames >= MAX_SILENCE_FRAMES) or force_process:
                    if force_process:
                        logger.info(f"[Voice] ⏱️ Max frames reached, forcing processing...")
                    logger.info(f"[Voice] 🔄 Processing speech... ({speech_frames} frames collected)")

                    # Recognize speech
                    text = self._recognize_text(bytes(speech_buffer))

                    if text:
                        print(f"\n{'='*60}")
                        print(f"[DEBUG VOICE] 📝 TEXT DETECTED: '{text}'")
                        print(f"[DEBUG VOICE] State: {self.state}")
                        print(f"{'='*60}\n")
                        logger.info(f"[Voice] 📝 Recognized text: '{text}'")

                        if self.state == VoiceState.IDLE:
                            # Check for wake word
                            if self._check_wake_word(text):
                                print(f"[DEBUG VOICE] ✅ WAKE WORD DETECTED!")
                                logger.info(f"[Voice] ✅ Wake word 'ORB' detected!")

                                if settings.VOICE_COMMANDS_ENABLED:
                                    print(f"[DEBUG VOICE] Moving to READY state")
                                    self._set_state(VoiceState.READY)
                                    await self._speak(settings.VOICE_RESPONSE_READY)
                                else:
                                    print(f"[DEBUG VOICE] ⚠️ Wake word detected but commands DISABLED")
                                    # Stay in IDLE state, don't speak
                            else:
                                print(f"[DEBUG VOICE] ❌ No wake word in: '{text}'")
                                logger.info(f"[Voice] ❌ No wake word in: '{text}' (say 'ORB!')")

                        elif self.state == VoiceState.READY:
                            # Try to recognize command
                            action = self._recognize_command(text)

                            if action:
                                print(f"[DEBUG VOICE] ✅ COMMAND RECOGNIZED: {action}")
                                logger.info(f"[Voice] ✅ Command recognized: {action}")

                                # Check if command execution is enabled
                                if settings.VOICE_COMMANDS_ENABLED:
                                    print(f"[DEBUG VOICE] Executing command (VOICE_COMMANDS_ENABLED=True)")
                                    self._set_state(VoiceState.PROCESSING)
                                    await self._execute_command(action)
                                    self._set_state(VoiceState.IDLE)
                                else:
                                    print(f"[DEBUG VOICE] ⚠️ Command execution DISABLED (VOICE_COMMANDS_ENABLED=False)")
                                    print(f"[DEBUG VOICE] Command '{action}' detected but NOT executed")
                                    self._set_state(VoiceState.IDLE)
                            else:
                                # Unknown/invalid command - ignore and stay in READY mode
                                print(f"[DEBUG VOICE] ⚠️ Invalid command ignored: '{text}' (staying in READY mode)")
                                logger.info(f"[Voice] Invalid command ignored: '{text}' (waiting for valid command or timeout)")
                                # Don't play error tone, don't change state - just keep waiting
                    else:
                        logger.info(f"[Voice] 🔇 Speech detected but no text recognized")

                    # Reset buffers
                    speech_buffer.clear()
                    speech_frames = 0
                    silence_frames = 0
                    if self.recognizer:
                        self.recognizer.Reset()

                # Limit buffer size
                if len(speech_buffer) > settings.VOICE_SAMPLE_RATE * 2 * 10:  # 10 seconds max
                    speech_buffer = speech_buffer[-settings.VOICE_SAMPLE_RATE * 2 * 5:]

                await asyncio.sleep(0.001)  # Yield to event loop

            except asyncio.CancelledError:
                logger.info("[Voice] Listen loop cancelled")
                break
            except Exception as e:
                logger.error(f"[Voice] Listen loop error: {e}")
                await asyncio.sleep(0.5)

        logger.info("[Voice] Listen loop stopped")

    def on_command_recognized(self, callback: Callable[[str, str], None]):
        """
        Register callback for when a voice command is recognized.

        Args:
            callback: Function(action, text) called when command recognized
        """
        self._on_command_callback = callback

    def on_state_change(self, callback: Callable[[VoiceState], None]):
        """
        Register callback for state changes.

        Args:
            callback: Function(state) called when state changes
        """
        self._on_state_change_callback = callback

    def get_status(self) -> dict:
        """Get current voice service status."""
        return {
            "is_running": self.is_running,
            "state": self.state.value,
            "mic_connected": self._mic_connected,
            "serial_connected": self._serial_connected,
            "vad_available": self._vad_available,
            "vosk_available": self._vosk_available,
            "tts_available": self._tts_available,
            "wake_word": settings.VOICE_WAKE_WORD,
            "available_commands": list(settings.VOICE_COMMANDS.keys()),
        }


# Factory function
def create_voice_service() -> VoiceService:
    """Create a voice service instance."""
    return VoiceService()


# Test the module
if __name__ == "__main__":
    import asyncio

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    async def test_voice():
        print("Voice Service Test")
        print("=" * 50)

        service = VoiceService()

        # Register callbacks
        def on_command(action, text):
            print(f"\n>>> COMMAND: {action}")

        def on_state(state):
            print(f"\n>>> STATE: {state.value}")

        service.on_command_recognized(on_command)
        service.on_state_change(on_state)

        # Start service
        if await service.start():
            print("\nVoice service started!")
            print(f"Status: {service.get_status()}")
            print("\nSay 'ORB!' to activate, then 'MUSIC', 'ANIME', or 'BOTH'")
            print("Press Ctrl+C to stop\n")

            try:
                await service.listen_loop()
            except KeyboardInterrupt:
                print("\nInterrupted!")
        else:
            print("Failed to start voice service")

        await service.stop()
        print("\nTest complete!")

    asyncio.run(test_voice())
