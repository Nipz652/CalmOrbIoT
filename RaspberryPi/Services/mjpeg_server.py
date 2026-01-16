"""
MJPEG Video Streaming Server

Streams video from the camera service as Motion JPEG over HTTP.
Used during live streaming sessions when Pi is in AP mode.

Endpoint: http://192.168.4.1:8080/video
Content-Type: multipart/x-mixed-replace; boundary=frame
"""

import asyncio
import logging
import time
from typing import Optional, Set
from aiohttp import web

# Import settings
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

logger = logging.getLogger(__name__)


class MJPEGServer:
    """
    MJPEG streaming server using aiohttp.

    Provides HTTP endpoint for MJPEG video stream that can be consumed
    by mobile apps or web browsers.
    """

    BOUNDARY = b"--frame"
    CONTENT_TYPE = "multipart/x-mixed-replace; boundary=frame"

    def __init__(
        self,
        port: int = None,
        resolution: tuple = None,
        fps: int = None,
        quality: int = None
    ):
        self.port = port or settings.STREAM_VIDEO_PORT
        self.resolution = resolution or settings.STREAM_VIDEO_RESOLUTION
        self.fps = fps or settings.STREAM_VIDEO_FPS
        self.quality = quality or settings.STREAM_VIDEO_QUALITY

        self.camera_service = None
        self.is_running = False
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None

        # Client tracking
        self._clients: Set[web.StreamResponse] = set()
        self._frame_interval = 1.0 / self.fps

        # Stats
        self.frames_streamed = 0
        self.clients_served = 0

    async def start(self, camera_service) -> bool:
        """
        Start the MJPEG streaming server.

        Args:
            camera_service: CameraService instance to capture frames from

        Returns:
            bool: True if server started successfully
        """
        if self.is_running:
            logger.warning("MJPEG server already running")
            return True

        self.camera_service = camera_service

        if not self.camera_service or not self.camera_service.is_running:
            logger.error("Camera service not available or not running")
            return False

        try:
            # Create aiohttp application
            self._app = web.Application()
            self._app.router.add_get('/video', self._handle_video_stream)
            self._app.router.add_get('/snapshot', self._handle_snapshot)
            self._app.router.add_get('/status', self._handle_status)
            self._app.router.add_get('/', self._handle_index)

            # Start server
            self._runner = web.AppRunner(self._app)
            await self._runner.setup()

            self._site = web.TCPSite(
                self._runner,
                '0.0.0.0',  # Bind to all interfaces
                self.port
            )
            await self._site.start()

            self.is_running = True
            logger.info(f"MJPEG server started on port {self.port}")
            logger.info(f"  Video stream: http://0.0.0.0:{self.port}/video")
            logger.info(f"  Snapshot: http://0.0.0.0:{self.port}/snapshot")
            logger.info(f"  Resolution: {self.resolution}, FPS: {self.fps}, Quality: {self.quality}")

            print(f"[MJPEG] Server started successfully on port {self.port}")
            print(f"[MJPEG] Resolution: {self.resolution}, FPS: {self.fps}, Quality: {self.quality}")
            print(f"[MJPEG] Camera service: {self.camera_service}")
            return True

        except Exception as e:
            logger.error(f"Failed to start MJPEG server: {e}")
            print(f"[MJPEG] ERROR: Failed to start server: {e}")
            import traceback
            traceback.print_exc()
            await self.stop()
            return False

    async def stop(self):
        """Stop the MJPEG streaming server."""
        logger.info("Stopping MJPEG server...")
        self.is_running = False

        # Close all client connections
        for client in list(self._clients):
            try:
                await client.write_eof()
            except Exception:
                pass
        self._clients.clear()

        # Shutdown server
        if self._site:
            await self._site.stop()
            self._site = None

        if self._runner:
            await self._runner.cleanup()
            self._runner = None

        self._app = None
        logger.info("MJPEG server stopped")

    async def _handle_index(self, request: web.Request) -> web.Response:
        """Handle root endpoint - returns simple HTML page."""
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Calm Orb Live Stream</title>
            <style>
                body {{ font-family: Arial, sans-serif; text-align: center; background: #1a1a2e; color: white; }}
                h1 {{ color: #4fd1c5; }}
                img {{ max-width: 100%; border-radius: 10px; }}
                .info {{ color: #888; margin: 10px; }}
            </style>
        </head>
        <body>
            <h1>Calm Orb Live Stream</h1>
            <img src="/video" alt="Live Stream" />
            <p class="info">Resolution: {self.resolution[0]}x{self.resolution[1]} @ {self.fps}fps</p>
            <p class="info">Connected clients: {len(self._clients)}</p>
        </body>
        </html>
        """
        return web.Response(text=html, content_type='text/html')

    async def _handle_video_stream(self, request: web.Request) -> web.StreamResponse:
        """
        Handle video stream request - returns MJPEG stream.

        The stream continues until the client disconnects or server stops.
        """
        logger.info(f"New video stream client: {request.remote}")
        print(f"[MJPEG] ===== NEW CLIENT CONNECTED: {request.remote} =====")
        print(f"[MJPEG] Camera service available: {self.camera_service is not None}")
        print(f"[MJPEG] Total clients served: {self.clients_served + 1}")
        self.clients_served += 1

        response = web.StreamResponse(
            status=200,
            reason='OK',
            headers={
                'Content-Type': self.CONTENT_TYPE,
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0',
                'Connection': 'keep-alive',
            }
        )

        await response.prepare(request)
        self._clients.add(response)

        print(f"[MJPEG] Client {request.remote} - Starting frame stream loop...")
        frame_count = 0

        try:
            while self.is_running:
                start_time = time.time()

                # Capture frame
                frame = self.camera_service.capture_jpeg_frame(
                    resolution=self.resolution,
                    quality=self.quality
                )

                if frame:
                    # Write MJPEG frame
                    try:
                        await response.write(
                            b"--frame\r\n"
                            b"Content-Type: image/jpeg\r\n"
                            b"Content-Length: " + str(len(frame)).encode() + b"\r\n"
                            b"\r\n" + frame + b"\r\n"
                        )
                        self.frames_streamed += 1
                        frame_count += 1

                        # Log every 30 frames (every 2 seconds at 15fps)
                        if frame_count % 30 == 0:
                            print(f"[MJPEG] Client {request.remote} - {frame_count} frames sent (size: {len(frame)} bytes)")
                    except (ConnectionResetError, ConnectionError):
                        logger.info(f"Client disconnected: {request.remote}")
                        print(f"[MJPEG] Client {request.remote} disconnected (sent {frame_count} frames)")
                        break
                else:
                    # No frame captured
                    if frame_count == 0:
                        print(f"[MJPEG] WARNING: No frame captured from camera (attempt {frame_count + 1})")
                    elif frame_count % 30 == 0:
                        print(f"[MJPEG] WARNING: Frame capture failed at frame {frame_count}")

                # Maintain frame rate
                elapsed = time.time() - start_time
                sleep_time = max(0, self._frame_interval - elapsed)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

        except asyncio.CancelledError:
            logger.info(f"Stream cancelled for client: {request.remote}")
            print(f"[MJPEG] Stream cancelled for {request.remote} (sent {frame_count} frames)")
        except Exception as e:
            logger.error(f"Stream error for client {request.remote}: {e}")
            print(f"[MJPEG] ERROR: Stream error for {request.remote}: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._clients.discard(response)
            logger.info(f"Client disconnected: {request.remote}")
            print(f"[MJPEG] Client {request.remote} fully disconnected (total frames sent: {frame_count})")

        return response

    async def _handle_snapshot(self, request: web.Request) -> web.Response:
        """Handle snapshot request - returns single JPEG image."""
        if not self.camera_service:
            return web.Response(status=503, text="Camera not available")

        frame = self.camera_service.capture_jpeg_frame(
            resolution=self.resolution,
            quality=self.quality
        )

        if frame:
            return web.Response(
                body=frame,
                content_type='image/jpeg',
                headers={'Cache-Control': 'no-cache'}
            )
        else:
            return web.Response(status=503, text="Failed to capture frame")

    async def _handle_status(self, request: web.Request) -> web.Response:
        """Handle status request - returns JSON status."""
        import json
        status = {
            "is_running": self.is_running,
            "port": self.port,
            "resolution": list(self.resolution),
            "fps": self.fps,
            "quality": self.quality,
            "connected_clients": len(self._clients),
            "frames_streamed": self.frames_streamed,
            "clients_served": self.clients_served,
        }
        return web.json_response(status)

    @property
    def client_count(self) -> int:
        """Get number of connected clients."""
        return len(self._clients)

    def get_status(self) -> dict:
        """Get server status."""
        return {
            "is_running": self.is_running,
            "port": self.port,
            "resolution": self.resolution,
            "fps": self.fps,
            "connected_clients": len(self._clients),
            "frames_streamed": self.frames_streamed,
        }


# Test the module
if __name__ == "__main__":
    import asyncio
    from camera_service import CameraService

    logging.basicConfig(level=logging.INFO)

    async def test_mjpeg():
        # Start camera
        camera = CameraService()
        if not await camera.start():
            print("Failed to start camera")
            return

        # Start MJPEG server
        server = MJPEGServer()
        if not await server.start(camera):
            print("Failed to start MJPEG server")
            await camera.stop()
            return

        print(f"\nMJPEG server running at http://localhost:{server.port}/video")
        print("Press Ctrl+C to stop...")

        try:
            while True:
                await asyncio.sleep(1)
                print(f"Clients: {server.client_count}, Frames: {server.frames_streamed}")
        except KeyboardInterrupt:
            print("\nStopping...")
        finally:
            await server.stop()
            await camera.stop()

    asyncio.run(test_mjpeg())
