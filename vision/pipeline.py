"""Video processing pipeline - ingestion, detection, tracking, attributes."""

import asyncio
import json
import threading
import time
from typing import Any, Callable

import cv2
import numpy as np

from attributes import extract_attributes
from config import VisionConfig
from detection import ObjectDetector
from tracker import ObjectTracker
from zones import ZoneManager


class VideoPipeline:
    """Main video processing pipeline.

    Handles frame capture, detection, tracking, attribute extraction,
    zone checking, and event emission.
    """

    def __init__(
        self,
        config: VisionConfig,
        on_frame_processed: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.config = config
        self.detector = ObjectDetector(config)
        self.tracker = ObjectTracker(config)
        self.zone_manager = ZoneManager(
            config_path=self._resolve_config_path("zones.json")
        )
        self.on_frame_processed = on_frame_processed

        self.running = False
        self.cap: cv2.VideoCapture | None = None
        self.frame_count = 0
        self.current_frame: np.ndarray | None = None
        self.current_results: dict[str, Any] | None = None
        self._last_frame_time = 0.0

        # Frame buffer for clip saving
        self.frame_buffer: list[tuple[float, np.ndarray]] = []
        self.max_buffer_seconds = 12  # Keep last 12 seconds

    def _resolve_config_path(self, filename: str) -> str:
        """Resolve config file path."""
        import os
        base = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base, "..", "config", filename)

    def open_source(self) -> bool:
        """Open the video source (file or RTSP stream)."""
        source = self.config.VIDEO_SOURCE
        print(f"[Pipeline] Opening video source: {source}")

        if source.startswith("rtsp://"):
            self.cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG)
        else:
            self.cap = cv2.VideoCapture(source)

        if not self.cap.isOpened():
            print(f"[Pipeline] ERROR: Cannot open video source: {source}")
            return False

        fps = self.cap.get(cv2.CAP_PROP_FPS) or 30
        width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"[Pipeline] Source opened: {width}x{height} @ {fps:.1f} FPS")
        print(f"[Pipeline] Processing target: {self.config.TARGET_FPS} FPS")
        return True

    def read_frame(self) -> np.ndarray | None:
        """Read and resize a single frame."""
        if self.cap is None or not self.cap.isOpened():
            return None

        ret, frame = self.cap.read()
        if not ret:
            return None

        # Resize for processing efficiency
        h, w = frame.shape[:2]
        target_w = self.config.FRAME_WIDTH
        if w != target_w:
            scale = target_w / w
            target_h = int(h * scale)
            frame = cv2.resize(frame, (target_w, target_h))

        return frame

    def process_frame(self, frame: np.ndarray) -> dict[str, Any]:
        """Process a single frame through the full pipeline.

        Returns complete results including detections, tracks, attributes, and zone events.
        """
        self.frame_count += 1
        timestamp = time.time()

        # Store frame in buffer for clip saving
        self.frame_buffer.append((timestamp, frame.copy()))
        cutoff = timestamp - self.max_buffer_seconds
        self.frame_buffer = [(t, f) for t, f in self.frame_buffer if t >= cutoff]

        # 1. Detection
        detection_results = self.detector.detect(frame)
        detection_results["frame_number"] = self.frame_count

        # 2. Tracking
        tracked_objects = []
        zone_events = []
        if self.config.TRACKING_ENABLED:
            tracked_objects = self.tracker.update(detection_results, frame)

            # 3. Attribute extraction + zone checking
            for obj in tracked_objects:
                attrs = extract_attributes(frame, obj, detection_results["frame_shape"])
                obj["attributes"] = attrs

                # Zone checking
                current_zones = self.zone_manager.check_zones(obj["center"])
                obj["zones"] = current_zones

                track_state = self.tracker.get_track_state(obj["track_id"])
                if track_state:
                    events = self.zone_manager.evaluate_zone_events(
                        obj["track_id"], current_zones, track_state
                    )
                    for evt in events:
                        evt["class"] = obj["class"]
                        evt["attributes"] = obj.get("attributes", {})
                        evt["timestamp"] = timestamp
                    zone_events.extend(events)

        # Person count (safety: only count, no identity)
        person_count = sum(1 for d in detection_results["detections"] if d["class"] == "person")

        results = {
            "timestamp": timestamp,
            "frame_number": self.frame_count,
            "elapsed_ms": detection_results["elapsed_ms"],
            "detections": detection_results["detections"],
            "tracked_objects": tracked_objects,
            "zone_events": zone_events,
            "person_count": person_count,
            "frame_shape": detection_results["frame_shape"],
        }

        self.current_frame = frame
        self.current_results = results

        return results

    def run_sync(self) -> None:
        """Run the pipeline loop in a synchronous blocking thread.

        This method is designed to be called from a background thread
        so it does not block the async event loop.
        """
        if not self.open_source():
            print("[Pipeline] Failed to open source, exiting")
            return

        self.running = True
        frame_interval = 1.0 / self.config.TARGET_FPS
        print(f"[Pipeline] Starting processing loop at {self.config.TARGET_FPS} FPS")

        while self.running:
            loop_start = time.time()

            frame = self.read_frame()
            if frame is None:
                # For video files, loop back to start
                if self.cap is not None:
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    frame = self.read_frame()
                    if frame is None:
                        print("[Pipeline] Cannot read frames, stopping")
                        break

            results = self.process_frame(frame)

            if self.on_frame_processed:
                try:
                    self.on_frame_processed(results)
                except Exception as e:
                    print(f"[Pipeline] Callback error: {e}")

            # Maintain target FPS
            elapsed = time.time() - loop_start
            sleep_time = max(0, frame_interval - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)

        self.cleanup()

    def start_background(self) -> threading.Thread:
        """Start the pipeline in a background daemon thread."""
        thread = threading.Thread(target=self.run_sync, daemon=True)
        thread.start()
        return thread

    def get_clip_frames(self, duration: float = 8.0) -> list[tuple[float, np.ndarray]]:
        """Get recent frames for video clip saving.

        Args:
            duration: How many seconds of video to return.

        Returns:
            List of (timestamp, frame) tuples.
        """
        if not self.frame_buffer:
            return []
        cutoff = time.time() - duration
        return [(t, f) for t, f in self.frame_buffer if t >= cutoff]

    def cleanup(self) -> None:
        """Release video capture resources."""
        self.running = False
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        print("[Pipeline] Cleaned up")

    def stop(self) -> None:
        """Signal the pipeline to stop."""
        self.running = False
