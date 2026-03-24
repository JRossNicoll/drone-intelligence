"""Video clip saver for event evidence."""

import os
import time
from typing import Any

import cv2
import numpy as np


class ClipSaver:
    """Saves short video clips when events occur."""

    def __init__(self, output_dir: str = "../data/clips", fps: int = 8) -> None:
        self.output_dir = os.path.abspath(output_dir)
        self.fps = fps
        os.makedirs(self.output_dir, exist_ok=True)
        print(f"[ClipSaver] Output directory: {self.output_dir}")

    def save_clip(
        self,
        frames: list[tuple[float, np.ndarray]],
        event_id: str,
        duration: float = 8.0,
    ) -> str | None:
        """Save a video clip from buffered frames.

        Args:
            frames: List of (timestamp, frame) tuples.
            event_id: Unique event identifier for filename.
            duration: Target clip duration in seconds.

        Returns:
            Path to saved clip file, or None on failure.
        """
        if not frames:
            print(f"[ClipSaver] No frames to save for event {event_id}")
            return None

        # Filter to requested duration
        end_time = frames[-1][0]
        start_time = end_time - duration
        clip_frames = [(t, f) for t, f in frames if t >= start_time]

        if not clip_frames:
            return None

        filename = f"event_{event_id}_{int(time.time())}.mp4"
        filepath = os.path.join(self.output_dir, filename)

        h, w = clip_frames[0][1].shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(filepath, fourcc, self.fps, (w, h))

        if not writer.isOpened():
            print(f"[ClipSaver] Failed to create video writer for {filepath}")
            return None

        for _, frame in clip_frames:
            writer.write(frame)

        writer.release()
        print(f"[ClipSaver] Saved clip: {filepath} ({len(clip_frames)} frames)")
        return filepath
