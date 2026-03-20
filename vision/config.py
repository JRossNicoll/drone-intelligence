"""Vision service configuration."""

import os
from pydantic_settings import BaseSettings


class VisionConfig(BaseSettings):
    """Configuration for the vision service."""

    # Video source: path to local file or RTSP URL
    VIDEO_SOURCE: str = os.environ.get("VIDEO_SOURCE", "sample.mp4")

    # Processing FPS target (5-10 recommended)
    TARGET_FPS: int = int(os.environ.get("TARGET_FPS", "8"))

    # YOLO model to use
    YOLO_MODEL: str = os.environ.get("YOLO_MODEL", "yolov8n.pt")

    # Detection confidence threshold
    CONFIDENCE_THRESHOLD: float = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.35"))

    # Backend API URL for sending events
    BACKEND_URL: str = os.environ.get("BACKEND_URL", "http://localhost:3000")

    # WebSocket port for streaming detections
    WS_PORT: int = int(os.environ.get("VISION_WS_PORT", "8765"))

    # FastAPI port
    API_PORT: int = int(os.environ.get("VISION_API_PORT", "8000"))

    # Frame resize width for processing
    FRAME_WIDTH: int = int(os.environ.get("FRAME_WIDTH", "960"))

    # Enable/disable tracking
    TRACKING_ENABLED: bool = os.environ.get("TRACKING_ENABLED", "true").lower() == "true"

    # ByteTrack parameters
    TRACK_THRESH: float = float(os.environ.get("TRACK_THRESH", "0.25"))
    TRACK_BUFFER: int = int(os.environ.get("TRACK_BUFFER", "30"))
    MATCH_THRESH: float = float(os.environ.get("MATCH_THRESH", "0.8"))

    class Config:
        env_file = ".env"
