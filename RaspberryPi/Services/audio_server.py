"""
WebSocket Audio Streaming Server

Streams audio from the I2S microphone (INMP441) over WebSocket.
Used during live streaming sessions when Pi is in AP mode.

Endpoint: ws://192.168.4.1:8081
Audio Format: 16-bit PCM, 16kHz, Mono
"""

import asyncio
import logging
import struct
import time
from typing import Optional, Set
from dataclasses import dataclass

# Try importing audio libraries
try:
    import sounddevice as sd
    import numpy as np
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False
    print("[Audio] Warning: sounddevice not available")

# Try importing websockets
try:
    import websockets
    from websockets.server import serve as ws_serve
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    print("[Audio] Warning: websockets not available")

# Import settings
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

logger = logging.getLogger(__name__)


@dataclass
class AudioConfig:
    """Audio configuration for I2S microphone."""
    sample_rate: int = 16000
    channels: int = 1
    chunk_size: int = 1024  # Samples per chunk
    bit_depth: int = 16
    device: Optional[str] = None  # None for default, or device name/index


class AudioServer:
    """
    WebSocket server for streaming audio from I2S microphone.

    Captures audio from the INMP441 I2S microphone and broadcasts
    to connected WebSocket clients in real-time.
    """

    def __init__(
        self,
        port: int = None,
        sample_rate: int = None,
        channels: int = None,
        chunk_size: int = None
    ):
        self.port = port or settings.STREAM_AUDIO_PORT
        self.sample_rate = sample_rate or settings.STREAM_AUDIO_SAMPLE_RATE
        self.channels = channels or settings.STREAM_AUDIO_CHANNELS
        self.chunk_size = chunk_size or settings.STREAM_AUDIO_CHUNK_SIZE

        self.is_running = False
        self._server = None
        self._audio_stream = None
        self._audio_queue: asyncio.Queue = None

        # Client tracking
        self._clients: Set = set()

        # Stats
        self.chunks_streamed = 0
        self.clients_served = 0

        # Audio device
        self._device = None

    def _find_i2s_device(self) -> Optional[int]:
        """Find the I2S microphone device index."""
        if not SOUNDDEVICE_AVAILABLE:
            return None

        try:
            devices = sd.query_devices()
            for i, dev in enumerate(devices):
                name = dev.get('name', '').lower()
                # Look for I2S or INMP441 device
                if 'i2s' in name or 'inmp' in name or 'snd_rpi' in name:
                    if dev.get('max_input_channels', 0) > 0:
                        logger.info(f"Found I2S device: {dev['name']} (index {i})")
                        return i

            # Fallback to default input device
            default = sd.query_devices(kind='input')
            if default:
                logger.info(f"Using default input device: {default['name']}")
                return None  # None means default

            return None

        except Exception as e:
            logger.error(f"Error finding audio device: {e}")
            return None

    async def start(self) -> bool:
        """
        Start the WebSocket audio streaming server.

        Returns:
            bool: True if server started successfully
        """
        if self.is_running:
            logger.warning("Audio server already running")
            return True

        if not WEBSOCKETS_AVAILABLE:
            logger.error("websockets library not available")
            return False

        if not SOUNDDEVICE_AVAILABLE:
            logger.error("sounddevice library not available")
            return False

        try:
            # Find audio device
            self._device = self._find_i2s_device()

            # Create audio queue for thread-safe communication
            self._audio_queue = asyncio.Queue(maxsize=50)

            # Start audio capture
            if not await self._start_audio_capture():
                return False

            # Start WebSocket server
            self._server = await ws_serve(
                self._handle_client,
                '0.0.0.0',
                self.port
            )

            self.is_running = True
            logger.info(f"Audio server started on port {self.port}")
            logger.info(f"  Sample rate: {self.sample_rate}Hz")
            logger.info(f"  Channels: {self.channels}")
            logger.info(f"  Chunk size: {self.chunk_size} samples")

            # Start broadcast task
            asyncio.create_task(self._broadcast_loop())

            return True

        except Exception as e:
            logger.error(f"Failed to start audio server: {e}")
            await self.stop()
            return False

    async def _start_audio_capture(self) -> bool:
        """Start capturing audio from microphone."""
        try:
            def audio_callback(indata, frames, time_info, status):
                """Called by sounddevice for each audio chunk."""
                if status:
                    logger.warning(f"Audio status: {status}")

                if self.is_running and self._audio_queue:
                    try:
                        # Convert to 16-bit PCM
                        audio_data = (indata * 32767).astype(np.int16)
                        # Put in queue (non-blocking)
                        self._audio_queue.put_nowait(audio_data.tobytes())
                    except asyncio.QueueFull:
                        pass  # Drop frame if queue is full

            # Open audio stream
            self._audio_stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype='float32',
                blocksize=self.chunk_size,
                device=self._device,
                callback=audio_callback
            )
            self._audio_stream.start()

            logger.info("Audio capture started")
            return True

        except Exception as e:
            logger.error(f"Failed to start audio capture: {e}")
            return False

    async def stop(self):
        """Stop the WebSocket audio streaming server."""
        logger.info("Stopping audio server...")
        self.is_running = False

        # Stop audio capture
        if self._audio_stream:
            try:
                self._audio_stream.stop()
                self._audio_stream.close()
            except Exception as e:
                logger.error(f"Error stopping audio stream: {e}")
            self._audio_stream = None

        # Close all client connections
        for client in list(self._clients):
            try:
                await client.close()
            except Exception:
                pass
        self._clients.clear()

        # Stop WebSocket server
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        # Clear queue
        if self._audio_queue:
            while not self._audio_queue.empty():
                try:
                    self._audio_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

        logger.info("Audio server stopped")

    async def _handle_client(self, websocket):
        """Handle new WebSocket client connection."""
        client_addr = websocket.remote_address
        logger.info(f"New audio client: {client_addr}")
        self.clients_served += 1
        self._clients.add(websocket)

        try:
            # Send audio configuration header
            config_msg = struct.pack(
                '<4sIHH',
                b'AUDC',  # Magic header
                self.sample_rate,
                self.channels,
                16  # Bit depth
            )
            await websocket.send(config_msg)

            # Keep connection alive until closed
            async for message in websocket:
                # Client can send control messages if needed
                pass

        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Audio client disconnected: {client_addr}")
        except Exception as e:
            logger.error(f"Audio client error {client_addr}: {e}")
        finally:
            self._clients.discard(websocket)

    async def _broadcast_loop(self):
        """Broadcast audio chunks to all connected clients."""
        logger.info("Audio broadcast loop started")

        while self.is_running:
            try:
                # Get audio chunk from queue
                audio_data = await asyncio.wait_for(
                    self._audio_queue.get(),
                    timeout=1.0
                )

                if not self._clients:
                    continue

                # Broadcast to all clients
                disconnected = set()
                for client in self._clients:
                    try:
                        await client.send(audio_data)
                        self.chunks_streamed += 1
                    except websockets.exceptions.ConnectionClosed:
                        disconnected.add(client)
                    except Exception as e:
                        logger.error(f"Broadcast error: {e}")
                        disconnected.add(client)

                # Remove disconnected clients
                self._clients -= disconnected

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Broadcast loop error: {e}")
                await asyncio.sleep(0.1)

        logger.info("Audio broadcast loop stopped")

    @property
    def client_count(self) -> int:
        """Get number of connected clients."""
        return len(self._clients)

    def get_status(self) -> dict:
        """Get server status."""
        return {
            "is_running": self.is_running,
            "port": self.port,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "chunk_size": self.chunk_size,
            "connected_clients": len(self._clients),
            "chunks_streamed": self.chunks_streamed,
            "sounddevice_available": SOUNDDEVICE_AVAILABLE,
            "websockets_available": WEBSOCKETS_AVAILABLE,
        }


class DummyAudioServer:
    """
    Dummy audio server for when audio hardware is not available.

    Returns success but doesn't actually stream audio.
    Used to allow video-only streaming.
    """

    def __init__(self, *args, **kwargs):
        self.is_running = False
        self.port = kwargs.get('port', settings.STREAM_AUDIO_PORT)

    async def start(self) -> bool:
        logger.warning("Audio hardware not available, using dummy server")
        self.is_running = True
        return True

    async def stop(self):
        self.is_running = False

    @property
    def client_count(self) -> int:
        return 0

    def get_status(self) -> dict:
        return {
            "is_running": self.is_running,
            "mode": "dummy",
            "reason": "Audio hardware not available",
        }


def create_audio_server(**kwargs) -> AudioServer:
    """
    Factory function to create audio server.

    Returns DummyAudioServer if audio libraries not available.
    """
    if SOUNDDEVICE_AVAILABLE and WEBSOCKETS_AVAILABLE:
        return AudioServer(**kwargs)
    else:
        return DummyAudioServer(**kwargs)


# Test the module
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    async def test_audio():
        print("Audio Server Test")
        print("=" * 40)

        # Check dependencies
        print(f"sounddevice available: {SOUNDDEVICE_AVAILABLE}")
        print(f"websockets available: {WEBSOCKETS_AVAILABLE}")

        if SOUNDDEVICE_AVAILABLE:
            print("\nAvailable audio devices:")
            for i, dev in enumerate(sd.query_devices()):
                if dev.get('max_input_channels', 0) > 0:
                    print(f"  [{i}] {dev['name']} (inputs: {dev['max_input_channels']})")

        # Create server
        server = create_audio_server()
        if not await server.start():
            print("Failed to start audio server")
            return

        print(f"\nAudio server running on ws://localhost:{server.port}")
        print("Press Ctrl+C to stop...")

        try:
            while True:
                await asyncio.sleep(1)
                status = server.get_status()
                print(f"Clients: {status.get('connected_clients', 0)}, "
                      f"Chunks: {status.get('chunks_streamed', 0)}")
        except KeyboardInterrupt:
            print("\nStopping...")
        finally:
            await server.stop()

    asyncio.run(test_audio())
