import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

from core.inference_worker import InferenceWorker
from core.robot_store import RobotStore

logger = logging.getLogger("pest_robot_server.stream")
router = APIRouter()


def get_robot_store(request: Request) -> RobotStore:
    return request.app.state.robot_store


def get_inference_worker(request: Request) -> InferenceWorker:
    return request.app.state.inference_worker


def _resolve_model_name(websocket: WebSocket) -> str:
    model_name = websocket.query_params.get("model")
    return model_name.strip() if model_name else "onnx"


async def _receive_initial_model(websocket: WebSocket) -> tuple[Optional[str], Optional[bytes]]:
    event = await websocket.receive()
    if event["type"] != "websocket.receive":
        return None, None
    if "text" in event:
        try:
            handshake = json.loads(event["text"])
            return handshake.get("model"), None
        except json.JSONDecodeError:
            return None, None
    if "bytes" in event:
        return None, event["bytes"]
    return None, None


@router.websocket("/ws/stream/{robot_id}")
async def stream_ws(robot_id: str, websocket: WebSocket, request: Request) -> None:
    await websocket.accept()
    store = get_robot_store(request)
    worker = get_inference_worker(request)

    client_ip = websocket.client.host if websocket.client else None
    store.update_status(robot_id, status="online", ip_address=client_ip)
    store.set_streaming(robot_id, True)

    async def send_detection(result: dict) -> None:
        await websocket.send_json(result)

    await worker.register_callback(robot_id, send_detection)

    model_name = _resolve_model_name(websocket)
    initial_frame = None
    if websocket.query_params.get("model") is None:
        try:
            model_name_candidate, initial_frame = await _receive_initial_model(websocket)
            if model_name_candidate:
                model_name = model_name_candidate
        except Exception:
            logger.debug("No initial model handshake received; using default %s", model_name)

    logger.info("Robot %s selected model %s for streaming", robot_id, model_name)

    try:
        if initial_frame:
            await worker.enqueue_frame(robot_id, initial_frame, model_name=model_name)
        while True:
            frame = await websocket.receive_bytes()
            if not frame:
                continue
            await worker.enqueue_frame(robot_id, frame, model_name=model_name)
    except WebSocketDisconnect:
        logger.info("Stream socket disconnected for %s", robot_id)
    except Exception as exc:
        logger.exception("Unhandled stream error for %s: %s", robot_id, exc)
    finally:
        await worker.unregister_callback(robot_id)
        await worker.flush_queue(robot_id)
        store.set_streaming(robot_id, False)
