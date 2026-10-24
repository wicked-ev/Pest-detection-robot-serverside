import asyncio
import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.auth import authorize_robot
from core.inference_worker import InferenceWorker
from core.model_adapters import ModelRegistry

logger = logging.getLogger("pest_robot_server.stream")
router = APIRouter()


async def _receive_initial_model(websocket: WebSocket) -> tuple[Optional[str], Optional[bytes]]:
    event = await websocket.receive()
    if event["type"] != "websocket.receive":
        return None, None
    if event.get("text"):
        try:
            handshake = json.loads(event["text"])
            return handshake.get("model"), None
        except json.JSONDecodeError:
            return None, None
    if event.get("bytes"):
        return None, event["bytes"]
    return None, None


def _resolve_model(requested: Optional[str], registry: ModelRegistry, worker: InferenceWorker, robot_id: str) -> str:
    """Pick the model once per connection instead of falling back on every frame."""
    requested = requested.strip() if requested else None
    if not requested:
        return worker.default_model_name
    try:
        registry.get(requested)
        return requested
    except KeyError:
        logger.warning(
            "Robot %s requested unknown model %s; using default %s",
            robot_id,
            requested,
            worker.default_model_name,
        )
        return worker.default_model_name


MAX_ROBOT_DETECTIONS = 100


def parse_robot_detections(payload: Any) -> Optional[dict]:
    """Turn a monitor-mode message from the robot into the server's result format.

    Expected: {"type": "detections", "image_size": [w, h],
               "detections": [{"class": str, "confidence": float, "bbox": [x1, y1, x2, y2]}, ...]}
    Returns None for anything malformed, so a bad message is skipped rather than stored.
    """
    if not isinstance(payload, dict) or payload.get("type") != "detections":
        return None
    items = payload.get("detections")
    size = payload.get("image_size")
    if not isinstance(items, list) or len(items) > MAX_ROBOT_DETECTIONS:
        return None
    if not (isinstance(size, list) and len(size) == 2 and all(isinstance(v, int) and v > 0 for v in size)):
        return None
    boxes, scores, labels = [], [], []
    try:
        for item in items:
            box = [float(v) for v in item["bbox"]]
            if len(box) != 4:
                return None
            boxes.append(box)
            scores.append(float(item["confidence"]))
            labels.append(str(item["class"]))
    except (KeyError, TypeError, ValueError):
        return None
    return {
        "boxes": boxes,
        "scores": scores,
        "labels": labels,
        "detections": [
            {"class": label, "confidence": score, "bbox": box} for box, score, label in zip(boxes, scores, labels)
        ],
        "image_size": size,
    }


async def _run_monitor_stream(websocket: WebSocket, robot_id: str, worker: InferenceWorker, hub) -> None:
    """Monitor mode: the robot runs its own model. Relay its frames; store its detections.

    A detections message is followed by the frame it was computed on, so the two are
    paired as they arrive (one websocket keeps messages in order).
    """
    pending: Optional[dict] = None
    while True:
        event = await websocket.receive()
        if event["type"] == "websocket.disconnect":
            raise WebSocketDisconnect(event.get("code", 1000))
        if event.get("text") is not None:
            try:
                pending = parse_robot_detections(json.loads(event["text"]))
            except json.JSONDecodeError:
                pending = None
            if pending is None:
                logger.warning("Ignoring malformed detections message from %s", robot_id)
            continue
        frame = event.get("bytes")
        if not frame:
            continue
        hub.publish_frame(robot_id, frame)
        if pending is not None:
            await worker.publish_result(robot_id, pending, frame, notify_robot=False)
            pending = None


async def _run_server_stream(websocket: WebSocket, robot_id: str, worker: InferenceWorker, hub, state, requested_model) -> None:
    """Server mode: run detection on the robot's frames and send results back to it."""
    initial_frame = None
    if requested_model is None:
        requested_model, initial_frame = await _receive_initial_model(websocket)
    model_name = _resolve_model(requested_model, state.model_registry, worker, robot_id)
    logger.info("Robot %s streaming with model %s", robot_id, model_name)

    if initial_frame:
        hub.publish_frame(robot_id, initial_frame)
        await worker.enqueue_frame(robot_id, initial_frame, model_name=model_name)
    while True:
        frame = await websocket.receive_bytes()
        if not frame:
            continue
        hub.publish_frame(robot_id, frame)
        await worker.enqueue_frame(robot_id, frame, model_name=model_name)


@router.websocket("/ws/stream/{robot_id}")
async def stream_ws(robot_id: str, websocket: WebSocket) -> None:
    """Robot side: receives JPEG frames, returns detections, relays frames to viewers."""
    if not await authorize_robot(websocket):
        return
    await websocket.accept()
    state = websocket.app.state
    store = state.robot_store
    worker: InferenceWorker = state.inference_worker
    hub = state.viewer_hub
    client_ip = websocket.client.host if websocket.client else None

    # A reconnecting robot replaces its stale connection.
    previous = state.stream_connections.get(robot_id)
    state.stream_connections[robot_id] = websocket
    if previous is not None:
        logger.info("Replacing previous stream connection for %s", robot_id)
        try:
            await previous.close(code=1001)
        except Exception:
            pass

    await asyncio.to_thread(store.ensure_robot, robot_id, client_ip)
    await asyncio.to_thread(store.set_streaming, robot_id, True)
    if state.stream_connections.get(robot_id) is not websocket:
        # A newer connection replaced (and closed) this one while it was setting up.
        # Registering now would overwrite the newer connection's detection callback.
        logger.info("Stream connection for %s was replaced during setup", robot_id)
        return

    async def send_detection(result: dict) -> None:
        await websocket.send_json(result)

    await worker.register_callback(robot_id, send_detection)

    # "monitor": the robot detects and sends results; otherwise the server detects.
    mode = "monitor" if websocket.query_params.get("mode") == "monitor" else "server"
    state.stream_modes[robot_id] = mode
    requested_model = websocket.query_params.get("model")
    try:
        if mode == "monitor":
            logger.info("Robot %s streaming in monitor mode (detection runs on the robot)", robot_id)
            await _run_monitor_stream(websocket, robot_id, worker, hub)
        else:
            await _run_server_stream(websocket, robot_id, worker, hub, state, requested_model)
    except WebSocketDisconnect:
        logger.info("Stream socket disconnected for %s", robot_id)
    except Exception as exc:
        logger.exception("Unhandled stream error for %s: %s", robot_id, exc)
    finally:
        # Shielded so cleanup completes even if this handler is cancelled (server shutdown).
        await asyncio.shield(_cleanup_stream(state, robot_id, websocket, send_detection))


async def _cleanup_stream(state, robot_id: str, websocket: WebSocket, send_detection) -> None:
    worker: InferenceWorker = state.inference_worker
    await worker.unregister_callback(robot_id, send_detection)
    # Online/offline is owned by the control socket's heartbeats, not by the stream.
    if state.stream_connections.get(robot_id) is websocket:
        del state.stream_connections[robot_id]
        state.stream_modes.pop(robot_id, None)
        await worker.flush_queue(robot_id)
        await asyncio.to_thread(state.robot_store.set_streaming, robot_id, False)


@router.websocket("/ws/view/{robot_id}")
async def view_ws(robot_id: str, websocket: WebSocket) -> None:
    """Dashboard side: receives the robot's JPEG frames (binary) and detections (JSON)."""
    await websocket.accept()
    await websocket.app.state.viewer_hub.serve(robot_id, websocket)
