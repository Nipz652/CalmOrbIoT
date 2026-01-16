#!/usr/bin/env python3
"""
Camera Service - Autism Behavior Detection using Roboflow

Uses Raspberry Pi camera with Roboflow AI model to detect autism-related behaviors.

Model: https://universe.roboflow.com/asddetection/autism-ximav
Classes (16):
    - Aggressive_Behavior, Avoid_Eye_Contact, Covering_Ears, Finger_Bitting,
    - Finger_Flicking, Hand_Clapping, Hand_Flapping, Head_Banging, Holding_Item,
    - Jumping, SIB_Bitting, Shaking_Legs, Toe_Walking, Tpot_Stimming, Twirling,
    - Weird_Expression
"""

import asyncio
import time
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass

# Try importing camera libraries
try:
    from picamera2 import Picamera2
    PICAMERA_AVAILABLE = True
except ImportError:
    PICAMERA_AVAILABLE = False
    print("[Camera] Warning: picamera2 not available")

# Try importing OpenCV for USB webcam support
try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    print("[Camera] Warning: OpenCV not available (USB webcam support disabled)")

# Try importing Roboflow
try:
    from inference import InferencePipeline
    from inference.core.interfaces.camera.entities import VideoFrame
    ROBOFLOW_AVAILABLE = True
except ImportError:
    ROBOFLOW_AVAILABLE = False
    print("[Camera] Warning: Roboflow inference not available")

# Fallback to HTTP API if inference SDK not available
try:
    import requests
    import base64
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

# Import settings
try:
    from config.settings import (
        CAMERA_TYPE,
        CAMERA_DEVICE_INDEX,
        CAMERA_RESOLUTION,
        CAMERA_FRAMERATE,
        ROBOFLOW_API_KEY,
        ROBOFLOW_MODEL_ID,
        ROBOFLOW_CONFIDENCE_THRESHOLD,
        BEHAVIOR_DETECTION_INTERVAL,
    )
except ImportError:
    # Default values if settings not available
    CAMERA_TYPE = "usb"  # Default to USB webcam
    CAMERA_DEVICE_INDEX = 0
    CAMERA_RESOLUTION = (640, 480)
    CAMERA_FRAMERATE = 30
    ROBOFLOW_API_KEY = ""
    ROBOFLOW_MODEL_ID = "autism-ximav/1"
    ROBOFLOW_CONFIDENCE_THRESHOLD = 0.5
    BEHAVIOR_DETECTION_INTERVAL = 1.0


# ======================
# Behavior Classes
# ======================

AUTISM_BEHAVIOR_CLASSES = [
    "Aggressive_Behavior",
    "Avoid_Eye_Contact",
    "Covering_Ears",
    "Finger_Bitting",
    "Finger_Flicking",
    "Hand_Clapping",
    "Hand_Flapping",
    "Head_Banging",
    "Holding_Item",
    "Jumping",
    "SIB_Bitting",
    "Shaking_Legs",
    "Toe_Walking",
    "Tpot_Stimming",
    "Twirling",
    "Weird_Expression",
]

# Behaviors that may indicate distress (could trigger calming response)
DISTRESS_BEHAVIORS = [
    "Aggressive_Behavior",
    "Head_Banging",
    "SIB_Bitting",
    "Covering_Ears",
    "Finger_Bitting",
]


@dataclass
class BehaviorDetection:
    """Represents a detected behavior."""
    label: str
    confidence: float
    timestamp: float
    bbox: Optional[tuple] = None  # (x, y, width, height)

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
            "bbox": self.bbox,
        }


class CameraService:
    """
    Camera service for autism behavior detection using Roboflow.

    Captures frames from Raspberry Pi camera and sends them to Roboflow
    for behavior classification. Updates BLE service with detection results.
    """

    def __init__(self):
        self.camera = None
        self.is_running = False
        self.pipeline = None
        self.camera_type = None  # Will be set to "usb" or "picamera" on start

        # Detection state
        self.last_detection: Optional[BehaviorDetection] = None
        self.detection_history: list = []
        self.max_history = 10

        # Callbacks
        self._on_behavior_detected: Optional[Callable] = None
        self._on_distress_behavior: Optional[Callable] = None

        # Configuration
        self.api_key = ROBOFLOW_API_KEY
        self.model_id = ROBOFLOW_MODEL_ID
        self.confidence_threshold = ROBOFLOW_CONFIDENCE_THRESHOLD
        self.detection_interval = BEHAVIOR_DETECTION_INTERVAL

        # Stats
        self.frames_processed = 0
        self.detections_count = 0

    def set_api_key(self, api_key: str):
        """Set Roboflow API key."""
        self.api_key = api_key

    def set_model_id(self, model_id: str):
        """Set Roboflow model ID (e.g., 'autism-ximav/1')."""
        self.model_id = model_id

    def on_behavior_detected(self, callback: Callable[[BehaviorDetection], None]):
        """Register callback for behavior detection events."""
        self._on_behavior_detected = callback

    def on_distress_behavior(self, callback: Callable[[BehaviorDetection], None]):
        """Register callback for distress behavior events."""
        self._on_distress_behavior = callback

    async def start(self) -> bool:
        """Initialize camera and start behavior detection."""
        if not self.api_key:
            print("[Camera] ERROR: Roboflow API key not set!")
            print("[Camera] Set ROBOFLOW_API_KEY in config/settings.py")
            return False

        print(f"[Camera] Starting camera service")
        print(f"[Camera] Camera type: {CAMERA_TYPE}")
        print(f"[Camera] Resolution: {CAMERA_RESOLUTION}")
        print(f"[Camera] Model: {self.model_id}")
        print(f"[Camera] Confidence threshold: {self.confidence_threshold}")

        # Initialize camera based on configured type
        if CAMERA_TYPE == "usb":
            # USB webcam via OpenCV
            if not OPENCV_AVAILABLE:
                print("[Camera] ERROR: OpenCV not available for USB webcam")
                print("[Camera] Install with: pip install opencv-python")
                return False
            try:
                self.camera = cv2.VideoCapture(CAMERA_DEVICE_INDEX)
                self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_RESOLUTION[0])
                self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_RESOLUTION[1])
                self.camera.set(cv2.CAP_PROP_FPS, CAMERA_FRAMERATE)
                if not self.camera.isOpened():
                    print(f"[Camera] Failed to open USB webcam at /dev/video{CAMERA_DEVICE_INDEX}")
                    return False
                self.camera_type = "usb"
                print(f"[Camera] USB webcam initialized (device index: {CAMERA_DEVICE_INDEX})")
            except Exception as e:
                print(f"[Camera] USB webcam error: {e}")
                return False
        elif CAMERA_TYPE == "picamera":
            # Pi Camera Module via Picamera2
            if not PICAMERA_AVAILABLE:
                print("[Camera] ERROR: picamera2 not available for Pi Camera")
                print("[Camera] Install with: pip install picamera2")
                return False
            try:
                self.camera = Picamera2()
                config = self.camera.create_preview_configuration(
                    main={"size": CAMERA_RESOLUTION, "format": "RGB888"}
                )
                self.camera.configure(config)
                self.camera.start()
                self.camera_type = "picamera"
                print("[Camera] Picamera2 initialized")
            except Exception as e:
                print(f"[Camera] Failed to initialize Picamera2: {e}")
                return False
        else:
            print(f"[Camera] ERROR: Unknown camera type '{CAMERA_TYPE}'")
            print("[Camera] Valid options: 'usb' or 'picamera'")
            return False

        self.is_running = True
        print("[Camera] Service started")
        return True

    async def stop(self):
        """Stop camera and release resources."""
        print("[Camera] Stopping camera service")
        self.is_running = False

        if self.camera:
            try:
                if self.camera_type == "usb":
                    # USB webcam (OpenCV)
                    self.camera.release()
                elif self.camera_type == "picamera":
                    # Pi Camera Module (Picamera2)
                    self.camera.stop()
                    self.camera.close()
            except Exception as e:
                print(f"[Camera] Error stopping camera: {e}")
            self.camera = None

        if self.pipeline:
            try:
                self.pipeline.terminate()
            except Exception:
                pass
            self.pipeline = None

        print("[Camera] Service stopped")

    def capture_frame(self) -> Optional[Any]:
        """Capture a single frame from the camera."""
        if not self.camera:
            if not hasattr(self, '_no_camera_logged'):
                print(f"[Camera] capture_frame: camera is None")
                self._no_camera_logged = True
            return None

        try:
            if self.camera_type == "usb":
                # USB webcam (OpenCV) - returns BGR, need to convert to RGB
                ret, frame = self.camera.read()
                if ret and frame is not None:
                    # Convert BGR to RGB (OpenCV uses BGR by default)
                    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                else:
                    # Log read failure once
                    if not hasattr(self, '_read_fail_logged'):
                        print(f"[Camera] camera.read() failed - ret={ret}, frame={'None' if frame is None else 'exists'}")
                        self._read_fail_logged = True
                    return None
            elif self.camera_type == "picamera":
                # Pi Camera Module (Picamera2) - returns RGB888
                return self.camera.capture_array()
            else:
                return None
        except Exception as e:
            print(f"[Camera] Frame capture error: {e}")
            import traceback
            traceback.print_exc()
            return None

    def capture_jpeg_frame(
        self,
        resolution: tuple = None,
        quality: int = 70
    ) -> Optional[bytes]:
        """
        Capture a frame and encode as JPEG for streaming.

        Args:
            resolution: Target resolution (width, height) or None for original
            quality: JPEG quality 0-100

        Returns:
            JPEG encoded bytes or None on failure
        """
        frame = self.capture_frame()
        if frame is None:
            # Only log first failure to avoid spam
            if not hasattr(self, '_jpeg_fail_logged'):
                print(f"[Camera] capture_jpeg_frame: capture_frame() returned None")
                self._jpeg_fail_logged = True
            return None

        try:
            # Convert RGB to BGR for OpenCV encoding
            bgr_frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

            # Resize if requested
            if resolution and resolution != (frame.shape[1], frame.shape[0]):
                bgr_frame = cv2.resize(bgr_frame, resolution)

            # Encode as JPEG
            encode_params = [cv2.IMWRITE_JPEG_QUALITY, quality]
            success, jpeg = cv2.imencode('.jpg', bgr_frame, encode_params)

            if success:
                # Log successful capture once
                if hasattr(self, '_jpeg_fail_logged'):
                    print(f"[Camera] Frame capture recovered - now working")
                    delattr(self, '_jpeg_fail_logged')
                return jpeg.tobytes()
            else:
                if not hasattr(self, '_encode_fail_logged'):
                    print(f"[Camera] JPEG encoding failed")
                    self._encode_fail_logged = True
                return None

        except Exception as e:
            print(f"[Camera] JPEG capture error: {e}")
            import traceback
            traceback.print_exc()
            return None

    async def run_detection_loop(self):
        """Main detection loop - captures frames and runs inference."""
        print("[Camera] Starting behavior detection loop")

        while self.is_running:
            try:
                await self._process_frame()
                await asyncio.sleep(self.detection_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[Camera] Detection loop error: {e}")
                await asyncio.sleep(1)

        print("[Camera] Detection loop stopped")

    async def _process_frame(self):
        """Process a single frame for behavior detection."""
        frame = self.capture_frame()

        if frame is None:
            return

        self.frames_processed += 1

        # Run inference
        detection = await self._run_inference(frame)

        if detection:
            self.last_detection = detection
            self.detections_count += 1

            # Add to history
            self.detection_history.append(detection)
            if len(self.detection_history) > self.max_history:
                self.detection_history.pop(0)

            # Notify callbacks
            if self._on_behavior_detected:
                self._on_behavior_detected(detection)

            # Check for distress behaviors
            if detection.label in DISTRESS_BEHAVIORS:
                print(f"[Camera] DISTRESS BEHAVIOR: {detection.label} ({detection.confidence:.2f})")
                if self._on_distress_behavior:
                    self._on_distress_behavior(detection)

    async def _run_inference(self, frame) -> Optional[BehaviorDetection]:
        """Run Roboflow inference on a frame."""
        try:
            if ROBOFLOW_AVAILABLE:
                return await self._run_inference_sdk(frame)
            elif REQUESTS_AVAILABLE:
                return await self._run_inference_http(frame)
            else:
                print("[Camera] No inference method available")
                return None
        except Exception as e:
            print(f"[Camera] Inference error: {e}")
            return None

    async def _run_inference_sdk(self, frame) -> Optional[BehaviorDetection]:
        """Run inference using Roboflow SDK."""
        # Import here to avoid issues if not installed
        from inference_sdk import InferenceHTTPClient

        client = InferenceHTTPClient(
            api_url="https://detect.roboflow.com",
            api_key=self.api_key,
        )

        # Run in executor to avoid blocking
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: client.infer(frame, model_id=self.model_id)
        )

        return self._parse_roboflow_result(result)

    async def _run_inference_http(self, frame) -> Optional[BehaviorDetection]:
        """Run inference using HTTP API (fallback)."""
        import cv2
        import numpy as np

        # Encode frame as JPEG
        _, buffer = cv2.imencode('.jpg', frame)
        img_base64 = base64.b64encode(buffer).decode('utf-8')

        # API endpoint
        url = f"https://detect.roboflow.com/{self.model_id}"

        params = {
            "api_key": self.api_key,
            "confidence": self.confidence_threshold,
        }

        # Run in executor to avoid blocking
        loop = asyncio.get_event_loop()

        def make_request():
            response = requests.post(
                url,
                params=params,
                data=img_base64,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10,
            )
            return response.json()

        result = await loop.run_in_executor(None, make_request)
        return self._parse_roboflow_result(result)

    def _parse_roboflow_result(self, result: dict) -> Optional[BehaviorDetection]:
        """Parse Roboflow API response into BehaviorDetection."""
        predictions = result.get("predictions", [])

        if not predictions:
            return None

        # Get highest confidence prediction
        best = max(predictions, key=lambda p: p.get("confidence", 0))

        confidence = best.get("confidence", 0)
        if confidence < self.confidence_threshold:
            return None

        label = best.get("class", "unknown")

        # Get bounding box if available
        bbox = None
        if all(k in best for k in ["x", "y", "width", "height"]):
            bbox = (
                best["x"] - best["width"] / 2,  # Convert center to top-left
                best["y"] - best["height"] / 2,
                best["width"],
                best["height"],
            )

        return BehaviorDetection(
            label=label,
            confidence=confidence,
            timestamp=time.time(),
            bbox=bbox,
        )

    def get_latest_detection(self) -> Optional[Dict]:
        """Get the most recent detection as a dict."""
        if self.last_detection:
            return self.last_detection.to_dict()
        return None

    def get_detection_for_ble(self) -> tuple:
        """Get detection data formatted for BLE service.

        Returns:
            tuple: (behavior_label, confidence)
        """
        if self.last_detection:
            return (self.last_detection.label, self.last_detection.confidence)
        return ("none", 0.0)

    def get_status(self) -> dict:
        """Get current camera status."""
        return {
            "is_running": self.is_running,
            "camera_type": self.camera_type or CAMERA_TYPE,
            "resolution": CAMERA_RESOLUTION,
            "model_id": self.model_id,
            "frames_processed": self.frames_processed,
            "detections_count": self.detections_count,
            "last_detection": self.last_detection.to_dict() if self.last_detection else None,
            "picamera_available": PICAMERA_AVAILABLE,
            "opencv_available": OPENCV_AVAILABLE,
            "roboflow_available": ROBOFLOW_AVAILABLE or REQUESTS_AVAILABLE,
        }


# ======================
# Factory function
# ======================

def create_camera_service() -> CameraService:
    """Create camera service instance."""
    return CameraService()


# ======================
# Standalone test
# ======================

async def main():
    """Test the camera service."""
    print("=" * 50)
    print("Camera Service Test - Roboflow Autism Detection")
    print("=" * 50)

    # Check dependencies
    print(f"\nDependencies:")
    print(f"  - OpenCV: {'Available' if OPENCV_AVAILABLE else 'NOT AVAILABLE'}")
    print(f"  - Picamera2: {'Available' if PICAMERA_AVAILABLE else 'NOT AVAILABLE'}")
    print(f"  - Roboflow SDK: {'Available' if ROBOFLOW_AVAILABLE else 'NOT AVAILABLE'}")
    print(f"  - HTTP Requests: {'Available' if REQUESTS_AVAILABLE else 'NOT AVAILABLE'}")

    if not ROBOFLOW_API_KEY:
        print("\nERROR: ROBOFLOW_API_KEY not set!")
        print("Set it in config/settings.py or as environment variable")
        return

    print(f"\nConfiguration:")
    print(f"  - Camera type: {CAMERA_TYPE}")
    if CAMERA_TYPE == "usb":
        print(f"  - Device index: {CAMERA_DEVICE_INDEX} (/dev/video{CAMERA_DEVICE_INDEX})")
    print(f"  - Resolution: {CAMERA_RESOLUTION}")
    print(f"  - Model: {ROBOFLOW_MODEL_ID}")
    print(f"  - Confidence: {ROBOFLOW_CONFIDENCE_THRESHOLD}")
    print(f"  - Detection interval: {BEHAVIOR_DETECTION_INTERVAL}s")

    # Create service
    service = CameraService()

    # Register callbacks
    def on_behavior(detection: BehaviorDetection):
        print(f"\n[Detection] {detection.label} (confidence: {detection.confidence:.2f})")

    def on_distress(detection: BehaviorDetection):
        print(f"\n*** DISTRESS: {detection.label} ***")

    service.on_behavior_detected(on_behavior)
    service.on_distress_behavior(on_distress)

    # Start service
    success = await service.start()
    if not success:
        print("Failed to start camera service")
        return

    print("\n" + "=" * 50)
    print("Running behavior detection...")
    print("Press Ctrl+C to stop")
    print("=" * 50)

    try:
        await service.run_detection_loop()
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        await service.stop()

        print("\nStats:")
        status = service.get_status()
        print(f"  - Frames processed: {status['frames_processed']}")
        print(f"  - Detections: {status['detections_count']}")


if __name__ == "__main__":
    asyncio.run(main())
