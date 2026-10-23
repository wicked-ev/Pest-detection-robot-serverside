import asyncio
import logging
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from core.auth import authorize_robot
from core.model_adapters import ModelRegistry
from core.robot_store import RobotStore

logger = logging.getLogger("pest_robot_server.control")
router = APIRouter()

# "halt" stops the motors; "shutdown" powers the robot off (the Pi treats "stop" as shutdown too).
VALID_COMMANDS = {"start_stream", "stop_stream", "halt", "reboot", "shutdown"}
HEARTBEAT_TIMEOUT_SECONDS = 40.0


class RegisterRobotPayload(BaseModel):
    robot_id: str
    name: str
    ip_address: str


class RobotCommandPayload(BaseModel):
    command: str


def robot_json(robot: Any) -> Dict[str, Any]:
    data = robot.dict()
    # Stored as naive UTC; the "Z" stops browsers from reading it as local time.
    if data.get("last_seen") is not None:
        data["last_seen"] = data["last_seen"].isoformat() + "Z"
    return data


def get_robot_store(request: Request) -> RobotStore:
    return request.app.state.robot_store


def get_command_queues(request: Request) -> Dict[str, asyncio.Queue]:
    return request.app.state.command_queues


def get_model_registry(request: Request) -> ModelRegistry:
    return request.app.state.model_registry


@router.post("/api/robots/register")
async def register_robot(
    payload: RegisterRobotPayload,
    request: Request,
) -> Dict[str, Any]:
    store = get_robot_store(request)
    robot = store.register_robot(payload.robot_id, payload.name, payload.ip_address)
    command_queue = get_command_queues(request)
    command_queue.setdefault(payload.robot_id, asyncio.Queue())
    return robot_json(robot)


@router.get("/api/robots")
async def list_robots(request: Request) -> Any:
    store = get_robot_store(request)
    robots = store.get_all_robots()
    return [robot_json(robot) for robot in robots]


@router.get("/api/robots/{robot_id}")
async def get_robot(robot_id: str, request: Request) -> Any:
    store = get_robot_store(request)
    robot = store.get_robot(robot_id)
    if robot is None:
        raise HTTPException(status_code=404, detail="Robot not found")
    return robot_json(robot)


@router.get("/api/models")
async def list_models(request: Request) -> Any:
    registry = get_model_registry(request)
    return registry.list_models()


@router.get("/api/models/{model_name}")
async def get_model(model_name: str, request: Request) -> Any:
    registry = get_model_registry(request)
    try:
        adapter = registry.get(model_name)
    except KeyError:
        raise HTTPException(status_code=404, detail="Model not found")
    info = adapter.model_info()
    return {
        "name": info.name,
        "architecture": info.architecture,
        "path": str(info.path),
        "metadata": info.metadata,
    }


@router.get("/api/models/{model_name}/availability")
async def check_model_availability(model_name: str, request: Request) -> Dict[str, Any]:
    registry = get_model_registry(request)
    try:
        adapter = registry.get(model_name)
    except KeyError:
        raise HTTPException(status_code=404, detail="Model not found")

    info = adapter.model_info()
    loaded = adapter.is_loaded()
    return {
        "name": info.name,
        "architecture": info.architecture,
        "path": str(info.path),
        "exists": info.path.exists(),
        "loaded": loaded,
        "ready_for_detection": loaded and info.path.exists(),
        "metadata": info.metadata,
    }


@router.post("/api/robots/{robot_id}/command")
async def send_command(robot_id: str, payload: RobotCommandPayload, request: Request) -> Any:
    store = get_robot_store(request)
    robot = store.get_robot(robot_id)
    if robot is None:
        raise HTTPException(status_code=404, detail="Robot not found")
    if payload.command not in VALID_COMMANDS:
        raise HTTPException(status_code=400, detail="Invalid command")
    # Refuse rather than queue: a command left waiting would run whenever the robot next connects.
    if robot_id not in request.app.state.control_connections:
        raise HTTPException(status_code=409, detail="Robot is not connected")
    queue = get_command_queues(request).setdefault(robot_id, asyncio.Queue())
    await queue.put({"command": payload.command})
    logger.info("Queued command %s for robot %s", payload.command, robot_id)
    return {"status": "queued", "robot_id": robot_id, "command": payload.command}


@router.websocket("/ws/control/{robot_id}")
async def control_ws(robot_id: str, websocket: WebSocket) -> None:
    """Robot side only: the robot sends heartbeats and receives queued commands."""
    if not await authorize_robot(websocket):
        return
    await websocket.accept()
    client_ip = websocket.client.host if websocket.client else None
    # Do not set robot status to online here; status will be updated on heartbeat messages only
    store = websocket.app.state.robot_store
    connections = websocket.app.state.control_connections
    command_queues = websocket.app.state.command_queues
    queue = command_queues.setdefault(robot_id, asyncio.Queue())

    # A reconnecting robot replaces its stale connection, so only one socket consumes commands.
    previous = connections.get(robot_id)
    connections[robot_id] = websocket
    if previous is not None:
        logger.info("Replacing previous control connection for %s", robot_id)
        try:
            await previous.close(code=1001)
        except Exception:
            pass

    await asyncio.to_thread(store.ensure_robot, robot_id, client_ip)

    async def send_commands() -> None:
        while True:
            command = await queue.get()
            await websocket.send_json(command)

    send_task = asyncio.create_task(send_commands())

    try:
        while True:
            try:
                message = await asyncio.wait_for(websocket.receive_json(), timeout=HEARTBEAT_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                logger.warning(
                    "No heartbeat received from %s for %.0f seconds; closing control socket",
                    robot_id,
                    HEARTBEAT_TIMEOUT_SECONDS,
                )
                await websocket.close(code=1001)
                break
            if isinstance(message, dict) and message.get("type") == "heartbeat":
                # The Pi reports its state machine value as "state".
                status_text = message.get("state") or message.get("status", "ok")
                await asyncio.to_thread(
                    store.update_status,
                    robot_id,
                    status="online",
                    last_seen=datetime.utcnow(),
                    ip_address=client_ip,
                )
                logger.debug("Received heartbeat from %s: %s", robot_id, status_text)
            else:
                logger.debug("Received control message from %s: %s", robot_id, message)
    except WebSocketDisconnect:
        logger.info("Control socket disconnected for %s", robot_id)
    except Exception as exc:
        logger.exception("Unhandled error on control websocket for %s: %s", robot_id, exc)
    finally:
        send_task.cancel()
        # Skip if a newer connection for this robot has already taken over.
        if connections.get(robot_id) is websocket:
            del connections[robot_id]
            await asyncio.to_thread(store.update_status, robot_id, status="offline", last_seen=datetime.utcnow())
