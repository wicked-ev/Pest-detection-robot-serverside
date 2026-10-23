import hmac
import logging
import os

from fastapi import WebSocket

logger = logging.getLogger("pest_robot_server.auth")

ROBOT_KEY_HEADER = "x-robot-key"


def robot_key() -> str:
    return os.getenv("ROBOT_KEY", "").strip()


def warn_if_auth_disabled() -> None:
    if not robot_key():
        logger.warning(
            "ROBOT_KEY is not set: any device on the network can connect as a robot. "
            "Set ROBOT_KEY in server/.env and on the Pi to require it."
        )


async def authorize_robot(websocket: WebSocket) -> bool:
    """Reject the handshake and return False unless it presents the shared robot key.

    Call before accept(): closing an unaccepted socket answers the handshake with HTTP 403.
    The key travels in a header rather than the URL so it never appears in access logs.
    """
    expected = robot_key()
    if not expected:
        return True
    provided = websocket.headers.get(ROBOT_KEY_HEADER, "")
    if hmac.compare_digest(provided.encode(), expected.encode()):
        return True
    client = websocket.client.host if websocket.client else "unknown"
    logger.warning("Rejected robot connection to %s from %s: bad or missing robot key", websocket.url.path, client)
    await websocket.close(code=1008)
    return False
