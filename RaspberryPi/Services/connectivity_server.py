"""
Connectivity Check Server

Responds to phone connectivity checks (Android/iOS) to prevent
automatic disconnection from WiFi AP with no internet.

Runs on port 80 and responds to:
- Android: http://connectivitycheck.gstatic.com/generate_204
- iOS: http://captive.apple.com/hotspot-detect.html
"""

import asyncio
import logging
from aiohttp import web

logger = logging.getLogger(__name__)


class ConnectivityServer:
    """
    Simple HTTP server that responds to connectivity checks.
    Makes phones think the WiFi has internet access.
    """

    def __init__(self, port: int = 80):
        self.port = port
        self.app = None
        self.runner = None
        self.site = None
        self.is_running = False

    async def handle_android_check(self, request):
        """Handle Android connectivity check - returns 204 No Content"""
        logger.debug("Android connectivity check")
        return web.Response(status=204)

    async def handle_ios_check(self, request):
        """Handle iOS captive portal check - returns HTML"""
        logger.debug("iOS connectivity check")
        html = """<!DOCTYPE html>
<html><head><title>Success</title></head>
<body>Success</body></html>"""
        return web.Response(text=html, content_type='text/html')

    async def handle_catchall(self, request):
        """Catch all other requests"""
        logger.debug(f"Connectivity check from: {request.path}")
        # Return 204 for most connectivity checks
        return web.Response(status=204)

    async def start(self) -> bool:
        """Start the connectivity check server"""
        if self.is_running:
            logger.warning("Connectivity server already running")
            return True

        try:
            self.app = web.Application()

            # Android connectivity checks
            self.app.router.add_get('/generate_204', self.handle_android_check)
            self.app.router.add_get('/gen_204', self.handle_android_check)

            # iOS captive portal checks
            self.app.router.add_get('/hotspot-detect.html', self.handle_ios_check)
            self.app.router.add_get('/library/test/success.html', self.handle_ios_check)

            # Catch-all for other connectivity checks
            self.app.router.add_get('/{tail:.*}', self.handle_catchall)

            # Start server
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()

            self.site = web.TCPSite(self.runner, '0.0.0.0', self.port)
            await self.site.start()

            self.is_running = True
            logger.info(f"Connectivity check server started on port {self.port}")
            return True

        except PermissionError:
            logger.error(f"Permission denied for port {self.port}. Need sudo for port 80.")
            return False
        except Exception as e:
            logger.error(f"Failed to start connectivity server: {e}")
            return False

    async def stop(self):
        """Stop the connectivity check server"""
        if not self.is_running:
            return

        logger.info("Stopping connectivity check server...")

        try:
            if self.site:
                await self.site.stop()
            if self.runner:
                await self.runner.cleanup()

            self.is_running = False
            logger.info("Connectivity check server stopped")

        except Exception as e:
            logger.error(f"Error stopping connectivity server: {e}")


# Test the module
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    async def test():
        print("Testing Connectivity Check Server")
        print("=" * 40)

        server = ConnectivityServer(port=8080)  # Use 8080 for testing (no sudo needed)

        if await server.start():
            print(f"\nServer running on http://0.0.0.0:8080")
            print("Test URLs:")
            print("  Android: http://localhost:8080/generate_204")
            print("  iOS: http://localhost:8080/hotspot-detect.html")
            print("\nPress Ctrl+C to stop...")

            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                print("\nStopping...")

        await server.stop()

    asyncio.run(test())
