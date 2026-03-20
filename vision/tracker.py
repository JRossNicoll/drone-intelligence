"""Multi-object tracking module using ByteTrack via supervision."""

import time
from typing import Any

import numpy as np
import supervision as sv

from config import VisionConfig


class ObjectTracker:
    """ByteTrack-based multi-object tracker with dwell time and direction tracking."""

    def __init__(self, config: VisionConfig) -> None:
        self.config = config
        self.byte_tracker = sv.ByteTrack(
            track_activation_threshold=config.TRACK_THRESH,
            lost_track_buffer=config.TRACK_BUFFER,
            minimum_matching_threshold=config.MATCH_THRESH,
            frame_rate=config.TARGET_FPS,
        )

        # Track state: track_id -> {first_seen, last_seen, positions, class, zone_history}
        self.track_state: dict[int, dict[str, Any]] = {}
        print("[Tracker] ByteTrack initialized")

    def update(self, detections_data: dict[str, Any], frame: np.ndarray) -> list[dict[str, Any]]:
        """Update tracker with new detections.

        Returns list of tracked objects with IDs and metadata.
        """
        detections_list = detections_data.get("detections", [])
        timestamp = detections_data.get("timestamp", time.time())

        if not detections_list:
            self._age_tracks(timestamp)
            return []

        # Build supervision Detections object
        bboxes = np.array([d["bbox"] for d in detections_list], dtype=np.float32)
        confidences = np.array([d["confidence"] for d in detections_list], dtype=np.float32)
        class_ids = np.array([d["class_id"] for d in detections_list], dtype=int)

        sv_detections = sv.Detections(
            xyxy=bboxes,
            confidence=confidences,
            class_id=class_ids,
        )

        # Run ByteTrack
        tracked = self.byte_tracker.update_with_detections(sv_detections)

        tracked_objects = []
        active_track_ids = set()

        if tracked.tracker_id is not None and len(tracked.tracker_id) > 0:
            for i in range(len(tracked.tracker_id)):
                track_id = int(tracked.tracker_id[i])
                bbox = tracked.xyxy[i].tolist()
                bbox = [round(v, 1) for v in bbox]
                class_id = int(tracked.class_id[i]) if tracked.class_id is not None else -1
                confidence = float(tracked.confidence[i]) if tracked.confidence is not None else 0.0

                # Find matching detection for class name using bbox IoU
                # (class_id alone is ambiguous when detection.py relabels
                # some trucks as construction_equipment)
                class_name = "unknown"
                best_iou = 0.0
                for d in detections_list:
                    if d["class_id"] != class_id:
                        continue
                    iou = self._bbox_iou(bbox, d["bbox"])
                    if iou > best_iou:
                        best_iou = iou
                        class_name = d["class"]

                # Calculate bbox center
                cx = (bbox[0] + bbox[2]) / 2
                cy = (bbox[1] + bbox[3]) / 2

                # Update track state
                if track_id not in self.track_state:
                    self.track_state[track_id] = {
                        "first_seen": timestamp,
                        "last_seen": timestamp,
                        "positions": [(cx, cy, timestamp)],
                        "class": class_name,
                        "class_id": class_id,
                        "entered_zones": set(),
                        "current_zones": set(),
                        "exited": False,
                    }
                else:
                    state = self.track_state[track_id]
                    state["last_seen"] = timestamp
                    state["positions"].append((cx, cy, timestamp))
                    # Keep last 60 positions
                    if len(state["positions"]) > 60:
                        state["positions"] = state["positions"][-60:]

                active_track_ids.add(track_id)
                state = self.track_state[track_id]

                # Calculate movement direction
                direction = self._compute_direction(state["positions"])

                # Calculate dwell time
                dwell_time = round(timestamp - state["first_seen"], 1)

                tracked_objects.append({
                    "track_id": track_id,
                    "class": class_name,
                    "class_id": class_id,
                    "confidence": round(confidence, 3),
                    "bbox": bbox,
                    "center": [round(cx, 1), round(cy, 1)],
                    "direction": direction,
                    "dwell_time": dwell_time,
                    "first_seen": state["first_seen"],
                    "last_seen": timestamp,
                })

        self._age_tracks(timestamp, active_track_ids)

        return tracked_objects

    @staticmethod
    def _bbox_iou(a: list[float], b: list[float]) -> float:
        """Compute Intersection-over-Union between two [x1,y1,x2,y2] bboxes."""
        x1 = max(a[0], b[0])
        y1 = max(a[1], b[1])
        x2 = min(a[2], b[2])
        y2 = min(a[3], b[3])
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        area_a = (a[2] - a[0]) * (a[3] - a[1])
        area_b = (b[2] - b[0]) * (b[3] - b[1])
        union = area_a + area_b - inter
        return inter / union if union > 0 else 0.0

    def _compute_direction(self, positions: list[tuple[float, float, float]]) -> str:
        """Compute movement direction from recent positions."""
        if len(positions) < 3:
            return "stationary"

        # Use last 10 positions
        recent = positions[-10:]
        dx = recent[-1][0] - recent[0][0]
        dy = recent[-1][1] - recent[0][1]

        magnitude = (dx**2 + dy**2) ** 0.5
        if magnitude < 5.0:
            return "stationary"

        angle = np.degrees(np.arctan2(-dy, dx)) % 360

        if 337.5 <= angle or angle < 22.5:
            return "east"
        elif 22.5 <= angle < 67.5:
            return "northeast"
        elif 67.5 <= angle < 112.5:
            return "north"
        elif 112.5 <= angle < 157.5:
            return "northwest"
        elif 157.5 <= angle < 202.5:
            return "west"
        elif 202.5 <= angle < 247.5:
            return "southwest"
        elif 247.5 <= angle < 292.5:
            return "south"
        else:
            return "southeast"

    def _age_tracks(self, timestamp: float, active_ids: set[int] | None = None) -> None:
        """Mark stale tracks and clean up old ones."""
        if active_ids is None:
            active_ids = set()

        stale_ids = []
        for tid, state in self.track_state.items():
            if tid not in active_ids and (timestamp - state["last_seen"]) > 5.0:
                stale_ids.append(tid)

        for tid in stale_ids:
            del self.track_state[tid]

    def get_track_state(self, track_id: int) -> dict[str, Any] | None:
        """Get current state for a track."""
        return self.track_state.get(track_id)

    def get_all_track_states(self) -> dict[int, dict[str, Any]]:
        """Get all active track states."""
        return dict(self.track_state)
