"""
Data Models - JSON payload structures for communication
"""

from dataclasses import dataclass, asdict
from typing import Optional, List
from datetime import datetime


@dataclass
class SensorReading:
    """DHT22 sensor reading from Pi"""
    temperature: float
    humidity: float
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ESP32Data:
    """Data received from ESP32"""
    pressure: float = 0.0           # Pressure sensor value
    motion_detected: bool = False   # Motion sensor status
    latitude: float = 0.0           # GPS latitude
    longitude: float = 0.0          # GPS longitude
    is_playing_sound: bool = False  # Calming sound status
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FaceEvent:
    """Face recognition event"""
    recognized: bool
    name: Optional[str] = None
    confidence: float = 0.0
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PiHubData:
    """
    Main JSON payload sent from Pi to Mobile App
    This aggregates all data from Pi sensors and ESP32
    """
    # Pi sensor data
    temperature: float = 0.0
    humidity: float = 0.0

    # ESP32 data
    pressure: float = 0.0
    motion_detected: bool = False
    latitude: float = 0.0
    longitude: float = 0.0
    is_playing_sound: bool = False

    # Face recognition
    face_recognized: bool = False
    face_name: Optional[str] = None

    # System status
    pi_connected: bool = True
    esp32_connected: bool = False
    camera_active: bool = False
    voice_active: bool = False

    # Timestamp
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)

    def to_json(self) -> str:
        """Convert to JSON string"""
        import json
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict) -> "PiHubData":
        """Create instance from dictionary"""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def update_from_sensor(self, reading: SensorReading):
        """Update with sensor reading"""
        self.temperature = reading.temperature
        self.humidity = reading.humidity

    def update_from_esp32(self, esp32_data: ESP32Data):
        """Update with ESP32 data"""
        self.pressure = esp32_data.pressure
        self.motion_detected = esp32_data.motion_detected
        self.latitude = esp32_data.latitude
        self.longitude = esp32_data.longitude
        self.is_playing_sound = esp32_data.is_playing_sound
        self.esp32_connected = True

    def update_from_face_event(self, event: FaceEvent):
        """Update with face recognition event"""
        self.face_recognized = event.recognized
        self.face_name = event.name


# Command models for receiving data from mobile app
@dataclass
class SensorPayload:
    """
    Sensor data payload sent to mobile app.
    Contains pressure, temperature, and motion data from the stress ball.
    """
    type: str = "sensor"
    deviceId: str = "orb-01"
    sessionId: str = ""
    childId: str = ""
    timestamp: str = ""

    # Sensor data
    pressure: float = 0.0           # Pressure in PSI
    pressureType: str = "none"      # "none", "light", "moderate", "firm", "squeeze"
    temperature: float = 0.0        # Temperature in celsius
    motion: str = "none"            # "none", "gentle", "tremble", "shake", "impact"

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat() + "Z"

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        import json
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict) -> "SensorPayload":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @staticmethod
    def get_pressure_type(psi: float) -> str:
        """Convert PSI value to pressure type string."""
        if psi <= 0.5:
            return "none"
        elif psi <= 1.5:
            return "light"
        elif psi <= 2.5:
            return "moderate"
        elif psi <= 3.5:
            return "firm"
        else:
            return "squeeze"

    @staticmethod
    def get_motion_type(motion_str: str) -> str:
        """Convert ESP32 motion string to standardized motion type."""
        motion_mapping = {
            "None": "none",
            "Still": "none",
            "Gentle Movement": "gentle",
            "Tremble": "tremble",
            "Shake": "shake",
            "Violent Shake": "shake",
            "Impact": "impact",
            "Free Fall": "impact",
        }
        return motion_mapping.get(motion_str, "none")


@dataclass
class EmotionPayload:
    """
    Emotion detection payload sent to mobile app.
    Contains emotion classification results from analysis.
    """
    type: str = "emotion"
    deviceId: str = "orb-01"
    sessionId: str = ""
    childId: str = ""
    timestamp: str = ""

    # Emotion data
    emotionLabel: str = "neutral"   # "calm", "anxious", "distressed", "neutral"
    confidence: float = 0.0         # Confidence score 0.0 - 1.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat() + "Z"

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        import json
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict) -> "EmotionPayload":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class MobileCommand:
    """Command received from mobile app"""
    command: str                    # Command type
    data: Optional[dict] = None     # Command parameters

    # Possible commands:
    # - "play_sound": Tell ESP32 to play calming sound
    # - "stop_sound": Tell ESP32 to stop sound
    # - "get_status": Request full status update
    # - "start_stream": Start camera livestream
    # - "stop_stream": Stop camera livestream
    # - "register_face": Register new face (data contains name and image)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "MobileCommand":
        return cls(**data)
