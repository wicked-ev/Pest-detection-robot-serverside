import asyncio
import logging
from typing import Any, Dict, Optional, Set, Union

from fastapi import WebSocket

logger = logging.getLogger("pest_robot_server.viewer_hub")

Message = Union[bytes, dict]


class _Viewer:
    """One dashboard connection holding only the newest frame and detection.

    Each viewer has a dedicated sender task, so a slow browser only skips
    frames for itself and never blocks the robot's frame loop or other viewers.
    """

    def __init__(self, websocket: WebSocket) -> None:
        self.websocket = websocket
        self._frame: Optional[bytes] = None
        self._detection: Optional[dict] = None
        self._ready = asyncio.Event()

    def offer(self, message: Message) -> None:
        # Overwrite rather than queue: an unsent older frame is no longer worth sending.
        if isinstance(message, bytes):
            self._frame = message
        else:
            self._detection = message
        self._ready.set()

    async def run(self) -> None:
        while True:
            await self._ready.wait()
            self._ready.clear()
            detection, self._detection = self._detection, None
            frame, self._frame = self._frame, None
            if detection is not None:
                await self.websocket.send_json(detection)
            if frame is not None:
                await self.websocket.send_bytes(frame)


class ViewerHub:
    """Fans out a robot's camera frames and detections to dashboard viewers."""

    def __init__(self) -> None:
        self._viewers: Dict[str, Set[_Viewer]] = {}

    async def serve(self, robot_id: str, websocket: WebSocket) -> None:
        """Register a viewer and forward messages to it until it disconnects."""
        viewer = _Viewer(websocket)
        self._viewers.setdefault(robot_id, set()).add(viewer)
        logger.info("Viewer joined %s (%d watching)", robot_id, len(self._viewers[robot_id]))

        sender = asyncio.create_task(viewer.run())
        # Viewers send nothing; receiving only detects when the browser goes away.
        receiver = asyncio.create_task(self._drain(websocket))
        try:
            await asyncio.wait({sender, receiver}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            sender.cancel()
            receiver.cancel()
            viewers = self._viewers.get(robot_id)
            if viewers is not None:
                viewers.discard(viewer)
                if not viewers:
                    del self._viewers[robot_id]
            logger.info("Viewer left %s", robot_id)

    @staticmethod
    async def _drain(websocket: WebSocket) -> None:
        while True:
            event = await websocket.receive()
            if event["type"] == "websocket.disconnect":
                return

    def has_viewers(self, robot_id: str) -> bool:
        return bool(self._viewers.get(robot_id))

    def publish_frame(self, robot_id: str, jpeg_bytes: bytes) -> None:
        for viewer in self._viewers.get(robot_id, ()):
            viewer.offer(jpeg_bytes)

    def publish_json(self, robot_id: str, payload: Dict[str, Any]) -> None:
        for viewer in self._viewers.get(robot_id, ()):
            viewer.offer(payload)
