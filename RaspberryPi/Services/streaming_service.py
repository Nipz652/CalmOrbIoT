"""
Streaming Service Orchestrator

Coordinates the live streaming lifecycle:
1. Save Wi-Fi credentials
2. Switch to AP mode
3. Start video/audio streaming servers
4. Monitor streaming state
5. Stop servers and restore Wi-Fi

State Machine:
IDLE -> PREPARING -> READY -> ACTIVE -> STOPPING -> IDLE
                        \-> ERROR -> IDLE
"""

import asyncio
import logging
import time
from enum import IntEnum
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass

# Import streaming components
from .ap_manager import APManager, APState
from .mjpeg_server import MJPEGServer
from .audio_server import create_audio_server
from .connectivity_server import ConnectivityServer

# Import settings
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

logger = logging.getLogger(__name__)


class StreamState(IntEnum):
    """Streaming state machine states (matches mobile app enum)."""
    IDLE = 0
    PREPARING = 1
    READY = 2
    ACTIVE = 3
    STOPPING = 4
    ERROR = 5


@dataclass
class StreamStatus:
    """Current streaming status."""
    state: StreamState
    ap_ssid: str = ""
    ap_password: str = ""
    video_url: str = ""
    audio_url: str = ""
    video_clients: int = 0
    audio_clients: int = 0
    start_time: float = 0
    error_message: str = ""

    def to_dict(self) -> dict:
        return {
            "state": int(self.state),
            "stateName": self.state.name,
            "apSSID": self.ap_ssid,
            "apPassword": self.ap_password,
            "videoUrl": self.video_url,
            "audioUrl": self.audio_url,
            "videoClients": self.video_clients,
            "audioClients": self.audio_clients,
            "startTime": self.start_time,
            "duration": time.time() - self.start_time if self.start_time > 0 else 0,
            "errorMessage": self.error_message,
        }


class StreamingService:
    """
    Main streaming service orchestrator.

    Manages the complete lifecycle of live streaming sessions including
    Wi-Fi AP mode, video streaming, and audio streaming.
    """

    def __init__(self, camera_service=None):
        self.camera_service = camera_service

        # Components
        self.ap_manager = APManager()
        self.connectivity_server = ConnectivityServer(port=80)
        self.mjpeg_server = MJPEGServer()
        self.audio_server = create_audio_server()

        # State
        self._state = StreamState.IDLE
        self._start_time: float = 0
        self._error_message: str = ""

        # Callbacks
        self._on_state_change: Optional[Callable[[StreamState], None]] = None

        # Timeout handling
        self._timeout_task: Optional[asyncio.Task] = None
        self._client_check_task: Optional[asyncio.Task] = None

    @property
    def state(self) -> StreamState:
        return self._state

    @state.setter
    def state(self, new_state: StreamState):
        if new_state != self._state:
            old_state = self._state
            self._state = new_state
            logger.info(f"Stream state: {old_state.name} -> {new_state.name}")
            if self._on_state_change:
                self._on_state_change(new_state)

    def set_camera_service(self, camera_service):
        """Set the camera service for video streaming."""
        self.camera_service = camera_service

    def on_state_change(self, callback: Callable[[StreamState], None]):
        """Register callback for state change notifications."""
        self._on_state_change = callback

    async def start_streaming(self) -> bool:
        """
        Start the live streaming session.

        1. Save current Wi-Fi credentials
        2. Switch to AP mode
        3. Start MJPEG video server
        4. Start WebSocket audio server
        5. Start timeout monitoring

        Returns:
            bool: True if streaming started successfully
        """
        if self.state not in [StreamState.IDLE, StreamState.ERROR]:
            logger.warning(f"Cannot start streaming from state: {self.state.name}")
            return False

        logger.info("=" * 50)
        logger.info("Starting live streaming session...")
        logger.info("=" * 50)
        print("[Streaming] ===== STARTING LIVE STREAM =====")

        self.state = StreamState.PREPARING
        self._error_message = ""

        try:
            # Step 1: Verify camera service is available
            print("[Streaming] Step 0: Verifying camera service...")
            if not self.camera_service:
                raise Exception("Camera service not available")

            if not self.camera_service.is_running:
                logger.info("Starting camera service...")
                print("[Streaming] Camera not running, starting it...")
                if not await self.camera_service.start():
                    raise Exception("Failed to start camera service")

            print("[Streaming] Camera service ready")

            # Step 2: Save Wi-Fi credentials
            logger.info("Step 1/4: Saving Wi-Fi credentials...")
            print("[Streaming] Step 1/5: Saving Wi-Fi credentials...")
            if not self.ap_manager.save_wifi_credentials():
                raise Exception("Failed to save Wi-Fi credentials")

            # Step 3: Switch to AP mode
            logger.info("Step 2/5: Switching to AP mode...")
            print("[Streaming] Step 2/5: Switching to AP mode...")
            if not await self.ap_manager.start_ap():
                raise Exception("Failed to start AP mode")

            # Step 3.5: Start connectivity check server (prevents phone disconnection)
            logger.info("Step 3/5: Starting connectivity check server...")
            print("[Streaming] Step 3/5: Starting connectivity server...")
            if not await self.connectivity_server.start():
                logger.warning("Connectivity server failed (needs sudo for port 80)")
                print("[Streaming] Connectivity server failed (non-fatal)")

            # Step 4: Start MJPEG video server
            logger.info("Step 4/5: Starting video server...")
            print("[Streaming] Step 4/5: Starting MJPEG video server...")
            if not await self.mjpeg_server.start(self.camera_service):
                raise Exception("Failed to start video server")
            print("[Streaming] Video server started successfully")

            # Step 5: Start audio server
            logger.info("Step 5/5: Starting audio server...")
            print("[Streaming] Step 5/5: Starting audio server...")
            audio_started = await self.audio_server.start()
            if not audio_started:
                logger.warning("Audio server failed to start (video-only mode)")

            # Success!
            self._start_time = time.time()
            self.state = StreamState.READY

            # Get AP credentials
            creds = self.ap_manager.get_ap_credentials()
            logger.info("=" * 50)
            logger.info("Live streaming ready!")
            logger.info(f"  AP SSID: {creds['ssid']}")
            logger.info(f"  AP Password: {creds['password']}")
            logger.info(f"  Video: {creds['videoUrl']}")
            logger.info(f"  Audio: {creds['audioUrl']}")
            logger.info("=" * 50)
            print("[Streaming] ===== STREAM READY =====")
            print(f"[Streaming] AP SSID: {creds['ssid']}")
            print(f"[Streaming] AP Password: {creds['password']}")
            print(f"[Streaming] Video URL: {creds['videoUrl']}")
            print(f"[Streaming] Audio URL: {creds['audioUrl']}")

            # Start monitoring tasks
            self._start_monitoring()

            return True

        except Exception as e:
            logger.error(f"Failed to start streaming: {e}")
            print(f"[Streaming] ERROR: {e}")
            import traceback
            traceback.print_exc()
            self._error_message = str(e)
            self.state = StreamState.ERROR

            # Cleanup on failure
            await self._cleanup()
            return False

    async def stop_streaming(self) -> bool:
        """
        Stop the live streaming session.

        1. Stop timeout monitoring
        2. Stop video server
        3. Stop audio server
        4. Stop AP mode
        5. Restore Wi-Fi connection

        Returns:
            bool: True if streaming stopped successfully
        """
        if self.state == StreamState.IDLE:
            logger.info("Streaming already stopped")
            return True

        logger.info("=" * 50)
        logger.info("Stopping live streaming session...")
        logger.info("=" * 50)

        self.state = StreamState.STOPPING

        # Stop monitoring tasks
        self._stop_monitoring()

        # Cleanup all components
        await self._cleanup()

        # Calculate session duration
        if self._start_time > 0:
            duration = time.time() - self._start_time
            logger.info(f"Session duration: {duration:.1f} seconds")

        self._start_time = 0
        self.state = StreamState.IDLE

        logger.info("Live streaming stopped")
        return True

    async def _cleanup(self):
        """Clean up all streaming resources."""
        # Stop video server
        if self.mjpeg_server.is_running:
            logger.info("Stopping video server...")
            await self.mjpeg_server.stop()

        # Stop audio server
        if self.audio_server.is_running:
            logger.info("Stopping audio server...")
            await self.audio_server.stop()

        # Stop connectivity check server
        if self.connectivity_server.is_running:
            logger.info("Stopping connectivity check server...")
            await self.connectivity_server.stop()

        # Stop AP and restore Wi-Fi
        if self.ap_manager.is_ap_active():
            logger.info("Stopping AP mode...")
            await self.ap_manager.stop_ap()

            logger.info("Restoring Wi-Fi connection...")
            await self.ap_manager.restore_wifi()

    def _start_monitoring(self):
        """Start timeout and client monitoring tasks."""
        # Stream timeout task
        self._timeout_task = asyncio.create_task(self._timeout_monitor())

        # Client connection monitoring
        self._client_check_task = asyncio.create_task(self._client_monitor())

    def _stop_monitoring(self):
        """Stop monitoring tasks."""
        if self._timeout_task:
            self._timeout_task.cancel()
            self._timeout_task = None

        if self._client_check_task:
            self._client_check_task.cancel()
            self._client_check_task = None

    async def _timeout_monitor(self):
        """Monitor for stream timeout."""
        try:
            max_duration = settings.STREAM_TIMEOUT
            logger.info(f"Stream timeout set to {max_duration} seconds")

            while self.state in [StreamState.READY, StreamState.ACTIVE]:
                await asyncio.sleep(10)

                elapsed = time.time() - self._start_time
                if elapsed >= max_duration:
                    logger.warning(f"Stream timeout reached ({max_duration}s)")
                    await self.stop_streaming()
                    break

        except asyncio.CancelledError:
            pass

    async def _client_monitor(self):
        """Monitor client connections and update state."""
        try:
            no_client_start = None
            client_timeout = settings.STREAM_CLIENT_TIMEOUT

            while self.state in [StreamState.READY, StreamState.ACTIVE]:
                await asyncio.sleep(2)

                video_clients = self.mjpeg_server.client_count
                audio_clients = self.audio_server.client_count
                total_clients = video_clients + audio_clients

                # Update state based on client connections
                if total_clients > 0:
                    if self.state == StreamState.READY:
                        self.state = StreamState.ACTIVE
                        logger.info(f"Client connected! Video: {video_clients}, Audio: {audio_clients}")
                    no_client_start = None

                elif self.state == StreamState.ACTIVE:
                    # No clients connected
                    if no_client_start is None:
                        no_client_start = time.time()
                        logger.info("All clients disconnected, starting timeout...")

                    elif time.time() - no_client_start >= client_timeout:
                        logger.warning(f"No clients for {client_timeout}s, stopping stream")
                        await self.stop_streaming()
                        break

        except asyncio.CancelledError:
            pass

    def get_status(self) -> StreamStatus:
        """Get current streaming status."""
        creds = self.ap_manager.get_ap_credentials()

        return StreamStatus(
            state=self.state,
            ap_ssid=creds.get('ssid', ''),
            ap_password=creds.get('password', ''),
            video_url=creds.get('videoUrl', ''),
            audio_url=creds.get('audioUrl', ''),
            video_clients=self.mjpeg_server.client_count if self.mjpeg_server else 0,
            audio_clients=self.audio_server.client_count if self.audio_server else 0,
            start_time=self._start_time,
            error_message=self._error_message,
        )

    def get_status_dict(self) -> dict:
        """Get current streaming status as dictionary."""
        return self.get_status().to_dict()

    def get_ap_credentials(self) -> dict:
        """Get AP credentials for mobile app."""
        return self.ap_manager.get_ap_credentials()

    def is_streaming(self) -> bool:
        """Check if streaming is currently active."""
        return self.state in [StreamState.READY, StreamState.ACTIVE]


# Factory function
def create_streaming_service(camera_service=None) -> StreamingService:
    """Create a streaming service instance."""
    return StreamingService(camera_service)


# Test the module
if __name__ == "__main__":
    import asyncio

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    async def test_streaming():
        from camera_service import CameraService

        print("Streaming Service Test")
        print("=" * 50)

        # Create camera service
        camera = CameraService()

        # Create streaming service
        service = StreamingService(camera)

        # Register state change callback
        def on_state_change(state):
            print(f"\n>>> STATE CHANGED: {state.name}")

        service.on_state_change(on_state_change)

        # Start streaming
        print("\nStarting streaming...")
        success = await service.start_streaming()

        if success:
            print("\nStreaming started successfully!")
            status = service.get_status()
            print(f"Status: {status.to_dict()}")

            print("\nRunning for 60 seconds...")
            print("Press Ctrl+C to stop early")

            try:
                for i in range(60):
                    await asyncio.sleep(1)
                    status = service.get_status()
                    print(f"[{i+1}s] State: {status.state.name}, "
                          f"Video clients: {status.video_clients}, "
                          f"Audio clients: {status.audio_clients}")
            except KeyboardInterrupt:
                print("\nInterrupted!")

        # Stop streaming
        print("\nStopping streaming...")
        await service.stop_streaming()

        print("\nTest complete!")

    asyncio.run(test_streaming())
