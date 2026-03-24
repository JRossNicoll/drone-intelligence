"""Object detection module using YOLOv8."""

import time
from typing import Any

import numpy as np
from ultralytics import YOLO

from config import VisionConfig

# COCO class ID to our class mapping
# COCO: 0=person, 2=car, 5=bus, 7=truck, 8=boat
COCO_CLASS_MAP: dict[int, str] = {
    0: "person",
    2: "car",
    5: "bus",
    7: "truck",
    8: "boat",
}

# Construction equipment: map from COCO classes that could be construction
# In COCO, there's no direct excavator class, so we detect trucks in
# certain size ranges as potential construction equipment
CONSTRUCTION_COCO_IDS: set[int] = set()  # Extended in post-processing


class ObjectDetector:
    """YOLOv8-based object detector."""

    def __init__(self, config: VisionConfig) -> None:
        self.config = config
        self.model = YOLO(config.YOLO_MODEL)
        self.target_classes = list(COCO_CLASS_MAP.keys())
        print(f"[Detector] Loaded model: {config.YOLO_MODEL}")
        print(f"[Detector] Confidence threshold: {config.CONFIDENCE_THRESHOLD}")
        print(f"[Detector] Tracking classes: {list(COCO_CLASS_MAP.values())}")

    def detect(self, frame: np.ndarray) -> dict[str, Any]:
        """Run detection on a single frame.

        Returns structured detection results.
        """
        start_time = time.time()

        results = self.model(
            frame,
            conf=self.config.CONFIDENCE_THRESHOLD,
            classes=self.target_classes,
            verbose=False,
        )

        detections = []
        if results and len(results) > 0:
            result = results[0]
            boxes = result.boxes

            if boxes is not None and len(boxes) > 0:
                for i in range(len(boxes)):
                    cls_id = int(boxes.cls[i].item())
                    confidence = float(boxes.conf[i].item())
                    bbox = boxes.xyxy[i].cpu().numpy().tolist()
                    bbox = [round(v, 1) for v in bbox]

                    class_name = COCO_CLASS_MAP.get(cls_id, "unknown")

                    # Heuristic: large trucks might be construction equipment
                    if class_name == "truck":
                        width = bbox[2] - bbox[0]
                        height = bbox[3] - bbox[1]
                        area = width * height
                        frame_area = frame.shape[0] * frame.shape[1]
                        if area / frame_area > 0.15:
                            class_name = "construction_equipment"

                    detections.append({
                        "class": class_name,
                        "confidence": round(confidence, 3),
                        "bbox": bbox,
                        "class_id": cls_id,
                    })

        elapsed = time.time() - start_time

        return {
            "timestamp": time.time(),
            "elapsed_ms": round(elapsed * 1000, 1),
            "detections": detections,
            "frame_shape": list(frame.shape[:2]),
        }
