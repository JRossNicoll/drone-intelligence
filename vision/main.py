"""Vision service main application - FastAPI + WebSocket + Pipeline."""

import asyncio
import base64
import json
import time
from contextlib import asynccontextmanager
from typing import Any

import cv2
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from clip_saver import ClipSaver
from config import VisionConfig
from pipeline import VideoPipeline

# Global state
config = VisionConfig()
pipeline: VideoPipeline | None = None
clip_saver = ClipSaver(output_dir="../data/clips", fps=config.TARGET_FPS)
connected_ws: list[WebSocket] = []
latest_results: dict[str, Any] = {}
pipeline_thread = None
_event_loop: asyncio.AbstractEventLoop | None = None


async def _broadcast_results_async(results: dict[str, Any]) -> None:
    """Broadcast processing results to all connected WebSocket clients."""
    message = {
        "type": "frame_results",
        "timestamp": results["timestamp"],
        "frame_number": results["frame_number"],
        "elapsed_ms": results["elapsed_ms"],
        "detections": results["detections"],
        "tracked_objects": results["tracked_objects"],
        "zone_events": results["zone_events"],
        "person_count": results["person_count"],
        "frame_shape": results["frame_shape"],
    }

    data = json.dumps(message)
    disconnected = []
    for ws in connected_ws:
        try:
            await ws.send_text(data)
        except Exception:
            disconnected.append(ws)

    for ws in disconnected:
        if ws in connected_ws:
            connected_ws.remove(ws)


def on_frame_processed(results: dict[str, Any]) -> None:
    """Callback from pipeline thread - thread-safely schedules async broadcast."""
    global latest_results
    latest_results = results
    if _event_loop is not None:
        asyncio.run_coroutine_threadsafe(_broadcast_results_async(results), _event_loop)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - start/stop pipeline in background thread."""
    global pipeline, pipeline_thread, _event_loop

    _event_loop = asyncio.get_running_loop()
    pipeline = VideoPipeline(config=config, on_frame_processed=on_frame_processed)
    pipeline_thread = pipeline.start_background()
    print("[App] Pipeline started in background thread")

    yield

    if pipeline:
        pipeline.stop()
    if pipeline_thread:
        pipeline_thread.join(timeout=5)
    print("[App] Pipeline stopped")


app = FastAPI(
    title="Drone Intelligence Vision Service",
    description="Aerial perception system - object detection, tracking, and analysis",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check() -> dict[str, Any]:
    """Health check endpoint."""
    return {
        "status": "ok",
        "pipeline_running": pipeline is not None and pipeline.running,
        "frame_count": pipeline.frame_count if pipeline else 0,
        "config": {
            "video_source": config.VIDEO_SOURCE,
            "target_fps": config.TARGET_FPS,
            "model": config.YOLO_MODEL,
        },
    }


@app.get("/detections")
async def get_detections() -> dict[str, Any]:
    """Get latest detection results."""
    if not latest_results:
        return {"status": "waiting", "message": "No frames processed yet"}
    return {
        "status": "ok",
        "data": {
            "timestamp": latest_results.get("timestamp"),
            "frame_number": latest_results.get("frame_number"),
            "detections": latest_results.get("detections", []),
            "tracked_objects": latest_results.get("tracked_objects", []),
            "person_count": latest_results.get("person_count", 0),
        },
    }


@app.get("/tracks")
async def get_tracks() -> dict[str, Any]:
    """Get all active tracked objects."""
    if pipeline is None:
        return {"status": "error", "message": "Pipeline not running"}
    tracks = pipeline.tracker.get_all_track_states()
    # Convert sets to lists for JSON serialization
    serializable = {}
    for tid, state in tracks.items():
        serializable[str(tid)] = {
            "class": state.get("class"),
            "first_seen": state.get("first_seen"),
            "last_seen": state.get("last_seen"),
            "entered_zones": list(state.get("entered_zones", set())),
            "current_zones": list(state.get("current_zones", set())),
        }
    return {"status": "ok", "tracks": serializable}


@app.get("/frame")
async def get_current_frame() -> Any:
    """Get the current processed frame as JPEG."""
    if pipeline is None or pipeline.current_frame is None:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": "No frame available"},
        )

    frame = pipeline.current_frame.copy()
    results = pipeline.current_results

    # Draw overlays
    if results:
        frame = draw_overlays(frame, results)

    _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return StreamingResponse(
        iter([buffer.tobytes()]),
        media_type="image/jpeg",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/frame/raw")
async def get_raw_frame() -> Any:
    """Get the current frame without overlays as JPEG."""
    if pipeline is None or pipeline.current_frame is None:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": "No frame available"},
        )

    _, buffer = cv2.imencode(".jpg", pipeline.current_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return StreamingResponse(
        iter([buffer.tobytes()]),
        media_type="image/jpeg",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/video_feed")
async def video_feed() -> StreamingResponse:
    """MJPEG video stream endpoint."""
    async def generate():
        while True:
            if pipeline is not None and pipeline.current_frame is not None:
                frame = pipeline.current_frame.copy()
                results = pipeline.current_results
                if results:
                    frame = draw_overlays(frame, results)
                _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + buffer.tobytes()
                    + b"\r\n"
                )
            await asyncio.sleep(1.0 / config.TARGET_FPS)

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.post("/clip")
async def save_clip(event_id: str = "manual") -> dict[str, Any]:
    """Save a video clip from the frame buffer."""
    if pipeline is None:
        return {"status": "error", "message": "Pipeline not running"}

    frames = pipeline.get_clip_frames(duration=8.0)
    path = clip_saver.save_clip(frames, event_id)

    if path:
        return {"status": "ok", "clip_path": path}
    return {"status": "error", "message": "Failed to save clip"}


@app.get("/zones")
async def get_zones() -> dict[str, Any]:
    """Get configured zones."""
    if pipeline is None:
        return {"status": "error", "message": "Pipeline not running"}
    return {"status": "ok", "zones": pipeline.zone_manager.get_zones()}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    """WebSocket endpoint for real-time detection streaming."""
    await ws.accept()
    connected_ws.append(ws)
    print(f"[WS] Client connected. Total: {len(connected_ws)}")

    try:
        while True:
            # Keep connection alive, listen for commands
            data = await ws.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await ws.send_text(json.dumps({"type": "pong"}))
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        pass
    finally:
        if ws in connected_ws:
            connected_ws.remove(ws)
        print(f"[WS] Client disconnected. Total: {len(connected_ws)}")


def draw_overlays(frame: np.ndarray, results: dict[str, Any]) -> np.ndarray:
    """Draw bounding boxes, labels, and zone overlays on frame."""
    overlay = frame.copy()

    # Draw tracked objects
    for obj in results.get("tracked_objects", []):
        bbox = obj["bbox"]
        x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
        track_id = obj["track_id"]
        class_name = obj["class"]
        confidence = obj["confidence"]
        attrs = obj.get("attributes", {})
        color_name = attrs.get("color", "")
        dwell = obj.get("dwell_time", 0)

        # Color based on class
        colors = {
            "car": (0, 255, 0),
            "truck": (255, 165, 0),
            "bus": (255, 0, 255),
            "boat": (0, 255, 255),
            "person": (0, 0, 255),
            "construction_equipment": (0, 140, 255),
        }
        box_color = colors.get(class_name, (128, 128, 128))

        cv2.rectangle(overlay, (x1, y1), (x2, y2), box_color, 2)

        label = f"#{track_id} {class_name} {confidence:.0%}"
        if color_name and color_name != "other":
            label += f" [{color_name}]"
        if dwell > 2:
            label += f" {dwell:.0f}s"

        label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0]
        cv2.rectangle(
            overlay,
            (x1, y1 - label_size[1] - 6),
            (x1 + label_size[0] + 4, y1),
            box_color,
            -1,
        )
        cv2.putText(
            overlay,
            label,
            (x1 + 2, y1 - 4),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1,
        )

    # Draw person count
    person_count = results.get("person_count", 0)
    if person_count > 0:
        text = f"Persons: {person_count}"
        cv2.putText(overlay, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

    # Draw FPS
    elapsed = results.get("elapsed_ms", 0)
    fps_text = f"Processing: {elapsed:.0f}ms"
    cv2.putText(overlay, fps_text, (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

    return overlay


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=config.API_PORT,
        reload=False,
        log_level="info",
    )
