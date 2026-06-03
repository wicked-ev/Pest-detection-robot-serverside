import asyncio
import logging
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from core.model_adapters import ModelRegistry
from core.robot_store import RobotStore

logger = logging.getLogger("pest_robot_server.control")
router = APIRouter()

VALID_COMMANDS = {"start_stream", "stop_stream", "reboot", "stop"}


class RegisterRobotPayload(BaseModel):
    robot_id: str
    name: str
    ip_address: str


class RobotCommandPayload(BaseModel):
    command: str


class WifiPayload(BaseModel):
    ssid: str
    password: str


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
    # TODO: Add authentication for registration and command endpoints.
    return {"robot_id": robot.robot_id, "token": f"token-{robot.robot_id}"}


@router.get("/api/robots")
async def list_robots(request: Request) -> Any:
    store = get_robot_store(request)
    robots = store.get_all_robots()
    return [robot.dict() for robot in robots]


@router.get("/api/robots/{robot_id}")
async def get_robot(robot_id: str, request: Request) -> Any:
    store = get_robot_store(request)
    robot = store.get_robot(robot_id)
    if robot is None:
        raise HTTPException(status_code=404, detail="Robot not found")
    return robot.dict()


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


@router.post("/api/robots/{robot_id}/command")
async def send_command(robot_id: str, payload: RobotCommandPayload, request: Request) -> Any:
    store = get_robot_store(request)
    robot = store.get_robot(robot_id)
    if robot is None:
        raise HTTPException(status_code=404, detail="Robot not found")
    if payload.command not in VALID_COMMANDS:
        raise HTTPException(status_code=400, detail="Invalid command")
    queue = get_command_queues(request).setdefault(robot_id, asyncio.Queue())
    await queue.put({"command": payload.command})
    logger.info("Queued command %s for robot %s", payload.command, robot_id)
    return {"status": "queued", "robot_id": robot_id, "command": payload.command}


@router.post("/api/robots/{robot_id}/wifi")
async def send_wifi_credentials(robot_id: str, payload: WifiPayload, request: Request) -> Any:
    store = get_robot_store(request)
    robot = store.get_robot(robot_id)
    if robot is None:
        raise HTTPException(status_code=404, detail="Robot not found")
    if robot.status != "provisioning":
        raise HTTPException(status_code=400, detail="Robot is not in provisioning mode")
    queue = get_command_queues(request).setdefault(robot_id, asyncio.Queue())
    await queue.put({"command": "wifi_config", "ssid": payload.ssid, "password": payload.password})
    # TODO: Add mDNS discovery for provisioning mode and credential provisioning.
    logger.info("Queued WiFi configuration for provisioning robot %s", robot_id)
    return {"status": "queued", "robot_id": robot_id}


@router.websocket("/ws/control/{robot_id}")
async def control_ws(robot_id: str, websocket: WebSocket, request: Request) -> None:
    await websocket.accept()
    store = get_robot_store(request)
    command_queues = get_command_queues(request)
    queue = command_queues.setdefault(robot_id, asyncio.Queue())

    client_ip = websocket.client.host if websocket.client else None
    store.update_status(robot_id, status="online", ip_address=client_ip, last_seen=datetime.utcnow())

    async def send_commands() -> None:
        while True:
            command = await queue.get()
            await websocket.send_json(command)

    send_task = asyncio.create_task(send_commands())

    try:
        while True:
            message = await websocket.receive_json()
            if isinstance(message, dict) and message.get("type") == "heartbeat":
                status_text = message.get("status", "ok")
                store.update_status(robot_id, status="online", last_seen=datetime.utcnow(), ip_address=client_ip)
                logger.debug("Received heartbeat from %s: %s", robot_id, status_text)
    except WebSocketDisconnect:
        logger.info("Control socket disconnected for %s", robot_id)
    except Exception as exc:
        logger.exception("Unhandled error on control websocket for %s: %s", robot_id, exc)
    finally:
        send_task.cancel()
        store.update_status(robot_id, status="offline", last_seen=datetime.utcnow())
