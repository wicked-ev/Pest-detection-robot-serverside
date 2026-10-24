import asyncio
import logging
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from core.auth import authorize_robot
from core.model_adapters import ModelRegistry
from core.robot_store import RobotStore, utc_now

logger = logging.getLogger("pest_robot_server.control")
router = APIRouter()

# "halt" stops wheels and sprayer; "shutdown" stops the robot program (the Pi treats "stop" as shutdown too).
# "move" is hold-to-drive: the dashboard repeats it while a key is held and the robot stops
# by itself when the repeats stop.
VALID_COMMANDS = {"start_stream", "stop_stream", "halt", "reboot", "shutdown", "move", "spray", "set_auto_spray"}
# Fields the robot reports about itself (heartbeat and "live" messages).
LIVE_FIELDS = ("state", "motors", "auto_spray", "spraying", "driving")
HEARTBEAT_TIMEOUT_SECONDS = 40.0


class RegisterRobotPayload(BaseModel):
    robot_id: str
    name: str
    ip_address: Optional[str] = None


class RobotCommandPayload(BaseModel):
    command: str
    direction: Optional[Literal["forward", "backward", "left", "right", "stop"]] = None  # move
    speed: Optional[int] = Field(None, ge=10, le=100)  # move: percent of full speed
    duration: Optional[float] = Field(None, gt=0, le=5)  # spray: seconds
    enabled: Optional[bool] = None  # set_auto_spray


def robot_json(robot: Any, request: Request) -> Dict[str, Any]:
    data = robot.model_dump()
    # Live status the robot last reported (None while it is not connected).
    data["live"] = request.app.state.robot_live.get(robot.robot_id)
    # Where detection runs while the robot streams: "robot" (monitor mode), "server", or None.
    mode = request.app.state.stream_modes.get(robot.robot_id)
    data["detection_mode"] = {"monitor": "robot", "server": "server"}.get(mode)
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
    return robot_json(robot, request)


@router.get("/api/robots")
async def list_robots(request: Request) -> Any:
    store = get_robot_store(request)
    robots = store.get_all_robots()
    return [robot_json(robot, request) for robot in robots]


@router.get("/api/robots/{robot_id}")
async def get_robot(robot_id: str, request: Request) -> Any:
    store = get_robot_store(request)
    robot = store.get_robot(robot_id)
    if robot is None:
        raise HTTPException(status_code=404, detail="Robot not found")
    return robot_json(robot, request)


@router.delete("/api/robots/{robot_id}")
async def delete_robot(robot_id: str, request: Request) -> Dict[str, Any]:
    """Remove a robot from the list. Its detection history is kept."""
    if robot_id in request.app.state.control_connections or robot_id in request.app.state.stream_connections:
        # It would register itself again straight away.
        raise HTTPException(status_code=409, detail="Robot is connected; shut it down first")
    store = get_robot_store(request)
    if not await asyncio.to_thread(store.delete_robot, robot_id):
        raise HTTPException(status_code=404, detail="Robot not found")
    request.app.state.command_queues.pop(robot_id, None)
    return {"status": "deleted", "robot_id": robot_id}


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
    if payload.command == "move" and payload.direction is None:
        raise HTTPException(status_code=400, detail="move needs a direction")
    if payload.command == "set_auto_spray" and payload.enabled is None:
        raise HTTPException(status_code=400, detail="set_auto_spray needs enabled: true or false")
    # Refuse rather than queue: a command left waiting would run whenever the robot next connects.
    if robot_id not in request.app.state.control_connections:
        raise HTTPException(status_code=409, detail="Robot is not connected")
    queue = get_command_queues(request).setdefault(robot_id, asyncio.Queue())
    message = payload.model_dump(exclude_none=True)
    await queue.put(message)
    # Drive commands arrive several times a second; keep them out of the normal log.
    log = logger.debug if payload.command == "move" else logger.info
    log("Queued command %s for robot %s", message, robot_id)
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
        # Stop the old sender now: its receive loop may not notice the close for a while,
        # and until then it would compete with this connection for queued commands.
        previous_sender = getattr(previous.state, "command_sender", None)
        if previous_sender is not None:
            previous_sender.cancel()
        try:
            await previous.close(code=1001)
        except Exception:
            pass

    await asyncio.to_thread(store.ensure_robot, robot_id, client_ip)
    if connections.get(robot_id) is not websocket:
        # A newer connection replaced (and closed) this one while it was setting up;
        # starting a sender now would compete with it for queued commands.
        logger.info("Control connection for %s was replaced during setup", robot_id)
        return

    async def send_commands() -> None:
        while True:
            command = await queue.get()
            try:
                await websocket.send_json(command)
            except BaseException:
                # Not delivered (socket closing or task cancelled): keep it for the next connection.
                queue.put_nowait(command)
                raise

    send_task = asyncio.create_task(send_commands())
    websocket.state.command_sender = send_task

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
            message_type = message.get("type") if isinstance(message, dict) else None
            if message_type in ("heartbeat", "live"):
                _update_live(websocket.app.state, robot_id, message)
            if message_type == "heartbeat":
                # The Pi reports its state machine value as "state".
                status_text = message.get("state") or message.get("status", "ok")
                await asyncio.to_thread(
                    store.update_status,
                    robot_id,
                    status="online",
                    last_seen=utc_now(),
                    ip_address=client_ip,
                )
                logger.debug("Received heartbeat from %s: %s", robot_id, status_text)
            elif message_type == "spray":
                await _record_spray(websocket.app.state, robot_id, message)
            elif message_type != "live":
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
            websocket.app.state.robot_live.pop(robot_id, None)
            # Shielded so the write completes even if this handler is cancelled (server shutdown).
            await asyncio.shield(
                asyncio.to_thread(store.update_status, robot_id, status="offline", last_seen=utc_now())
            )


def _update_live(state, robot_id: str, message: Dict[str, Any]) -> None:
    live = state.robot_live.setdefault(robot_id, {})
    for field in LIVE_FIELDS:
        if field in message:
            live[field] = message[field]


async def _record_spray(state, robot_id: str, message: Dict[str, Any]) -> None:
    """Store a spray the robot reports and show it to anyone watching the robot."""
    try:
        duration = max(0.0, min(float(message.get("duration", 0.0)), 10.0))
        confidence = message.get("confidence")
        confidence = float(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        logger.warning("Ignoring malformed spray report from %s: %s", robot_id, message)
        return
    trigger = "auto" if message.get("trigger") == "auto" else "manual"
    label = str(message["label"])[:100] if message.get("label") else None
    record = await asyncio.to_thread(
        state.sightings.record_spray, robot_id, trigger, duration, label, confidence
    )
    state.viewer_hub.publish_json(robot_id, {"type": "spray", **record.model_dump(mode="json")})
