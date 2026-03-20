"""Attribute extraction layer for tracked objects."""

from typing import Any

import numpy as np


# Color ranges in HSV space for basic color classification
COLOR_RANGES: dict[str, list[tuple[np.ndarray, np.ndarray]]] = {
    "red": [
        (np.array([0, 70, 50]), np.array([10, 255, 255])),
        (np.array([170, 70, 50]), np.array([180, 255, 255])),
    ],
    "blue": [
        (np.array([100, 70, 50]), np.array([130, 255, 255])),
    ],
    "white": [
        (np.array([0, 0, 180]), np.array([180, 30, 255])),
    ],
    "black": [
        (np.array([0, 0, 0]), np.array([180, 255, 50])),
    ],
}


def classify_color(frame: np.ndarray, bbox: list[float]) -> str:
    """Classify the dominant color of an object from its bounding box region.

    Returns one of: black, white, red, blue, other.
    """
    import cv2

    h, w = frame.shape[:2]
    x1 = max(0, int(bbox[0]))
    y1 = max(0, int(bbox[1]))
    x2 = min(w, int(bbox[2]))
    y2 = min(h, int(bbox[3]))

    if x2 <= x1 or y2 <= y1:
        return "other"

    roi = frame[y1:y2, x1:x2]
    if roi.size == 0:
        return "other"

    # Shrink ROI to center 60% to avoid background
    rh, rw = roi.shape[:2]
    margin_x = int(rw * 0.2)
    margin_y = int(rh * 0.2)
    if margin_x > 0 and margin_y > 0:
        roi = roi[margin_y:rh - margin_y, margin_x:rw - margin_x]

    if roi.size == 0:
        return "other"

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

    best_color = "other"
    best_ratio = 0.0
    total_pixels = hsv.shape[0] * hsv.shape[1]

    if total_pixels == 0:
        return "other"

    for color_name, ranges in COLOR_RANGES.items():
        mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
        for lower, upper in ranges:
            mask |= cv2.inRange(hsv, lower, upper)
        ratio = np.count_nonzero(mask) / total_pixels
        if ratio > best_ratio and ratio > 0.3:
            best_ratio = ratio
            best_color = color_name

    return best_color


def classify_size(bbox: list[float], frame_shape: list[int]) -> str:
    """Classify object size as small/medium/large based on bbox area relative to frame.

    Args:
        bbox: [x1, y1, x2, y2]
        frame_shape: [height, width]
    """
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    area = width * height
    frame_area = frame_shape[0] * frame_shape[1]

    if frame_area == 0:
        return "medium"

    ratio = area / frame_area

    if ratio < 0.02:
        return "small"
    elif ratio < 0.10:
        return "medium"
    else:
        return "large"


def extract_attributes(
    frame: np.ndarray,
    tracked_object: dict[str, Any],
    frame_shape: list[int],
) -> dict[str, str]:
    """Extract attributes for a tracked object.

    Returns dict with 'color' and 'size' keys.
    """
    bbox = tracked_object["bbox"]
    obj_class = tracked_object.get("class", "unknown")

    # Only extract color for vehicles, not persons
    if obj_class == "person":
        color = "other"
    else:
        color = classify_color(frame, bbox)

    size = classify_size(bbox, frame_shape)

    return {
        "color": color,
        "size": size,
    }
