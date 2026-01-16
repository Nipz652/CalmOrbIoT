"""
Display Service - Handles screen animations and UI
"""

import asyncio
from config.settings import SCREEN_WIDTH, SCREEN_HEIGHT


class DisplayService:
    """Manages screen display and animations"""

    def __init__(self):
        self.screen = None
        self.is_running = False
        self.current_animation = None

    async def start(self):
        """Initialize display"""
        print(f"[Display] Starting display service ({SCREEN_WIDTH}x{SCREEN_HEIGHT})")
        # TODO: Initialize pygame or other display library
        self.is_running = True

    async def stop(self):
        """Stop display service"""
        print("[Display] Stopping display service")
        self.is_running = False
        # TODO: Cleanup display

    def show_animation(self, animation_name: str):
        """Play a specific animation"""
        print(f"[Display] Playing animation: {animation_name}")
        self.current_animation = animation_name
        # TODO: Load and play animation from assets/animations/

    def show_temperature(self, temperature: float, humidity: float):
        """Display current temperature and humidity"""
        print(f"[Display] Showing temp: {temperature}°C, humidity: {humidity}%")
        # TODO: Render temperature display

    def show_status(self, status: str):
        """Display status message"""
        print(f"[Display] Status: {status}")
        # TODO: Render status text

    def show_alert(self, message: str):
        """Display alert/notification"""
        print(f"[Display] Alert: {message}")
        # TODO: Render alert with animation

    def show_face_recognized(self, name: str):
        """Display face recognition result"""
        print(f"[Display] Face recognized: {name}")
        # TODO: Show welcome animation with name

    def clear(self):
        """Clear the display"""
        self.current_animation = None
        # TODO: Clear screen

    def get_status(self) -> dict:
        """Get display service status"""
        return {
            "is_running": self.is_running,
            "resolution": (SCREEN_WIDTH, SCREEN_HEIGHT),
            "current_animation": self.current_animation,
        }
