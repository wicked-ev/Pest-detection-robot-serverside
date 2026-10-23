import asyncio
import json
import logging
from typing import Optional

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

    async def send_detection(result: dict) -> None:
        await websocket.send_json(result)

    await worker.register_callback(robot_id, send_detection)

    requested_model = websocket.query_params.get("model")
    initial_frame = None
    try:
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
    except WebSocketDisconnect:
        logger.info("Stream socket disconnected for %s", robot_id)
    except Exception as exc:
        logger.exception("Unhandled stream error for %s: %s", robot_id, exc)
    finally:
        await worker.unregister_callback(robot_id, send_detection)
        # Online/offline is owned by the control socket's heartbeats, not by the stream.
        if state.stream_connections.get(robot_id) is websocket:
            del state.stream_connections[robot_id]
            await worker.flush_queue(robot_id)
            await asyncio.to_thread(store.set_streaming, robot_id, False)


@router.websocket("/ws/view/{robot_id}")
async def view_ws(robot_id: str, websocket: WebSocket) -> None:
    """Dashboard side: receives the robot's JPEG frames (binary) and detections (JSON)."""
    await websocket.accept()
    await websocket.app.state.viewer_hub.serve(robot_id, websocket)
