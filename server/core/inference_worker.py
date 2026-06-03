import asyncio
import io
import logging
from typing import Awaitable, Callable, Dict, Optional, Tuple

import numpy as np
from PIL import Image

from .model_adapters import ModelRegistry
from .robot_store import RobotStore

logger = logging.getLogger("pest_robot_server.inference_worker")


class InferenceWorker:
    """Background worker that processes frames and returns detections."""

    def __init__(
        self,
        model_registry: ModelRegistry,
        robot_store: RobotStore,
        max_queue_size: int = 2,
        default_model_name: str = "onnx",
    ) -> None:
        self.model_registry = model_registry
        self.robot_store = robot_store
        self.max_queue_size = max_queue_size
        self.default_model_name = default_model_name
        self._queues: Dict[str, asyncio.Queue[Tuple[bytes, str]]] = {}
        self._callbacks: Dict[str, Callable[[dict], Awaitable[None]]] = {}
        self._new_frame = asyncio.Event()
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        logger.info("Loading %d detection models", len(self.model_registry.list_models()))
        await asyncio.to_thread(self._load_models)
        logger.info("Loaded all detection models.")

    def _load_models(self) -> None:
        for model_name, adapter in self.model_registry.adapters().items():
            adapter.load()
            logger.info("Model %s loaded from %s", model_name, adapter.model_path)

    async def enqueue_frame(self, robot_id: str, jpeg_bytes: bytes, model_name: Optional[str] = None) -> None:
        if not model_name:
            model_name = self.default_model_name
        async with self._lock:
            queue = self._queues.setdefault(robot_id, asyncio.Queue(maxsize=self.max_queue_size))
            if queue.full():
                try:
                    queue.get_nowait()
                    logger.debug("Dropped oldest frame for robot %s", robot_id)
                except asyncio.QueueEmpty:
                    pass
            await queue.put((jpeg_bytes, model_name))
            self._new_frame.set()

    async def register_callback(self, robot_id: str, callback: Callable[[dict], Awaitable[None]]) -> None:
        async with self._lock:
            self._callbacks[robot_id] = callback

    async def unregister_callback(self, robot_id: str) -> None:
        async with self._lock:
            self._callbacks.pop(robot_id, None)

    async def flush_queue(self, robot_id: str) -> None:
        async with self._lock:
            queue = self._queues.get(robot_id)
            if queue is None:
                return
            while not queue.empty():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

    async def run(self, shutdown_event: asyncio.Event) -> None:
        model_names = [model["name"] for model in self.model_registry.list_models()]
        if not model_names:
            raise RuntimeError("Inference worker has no available models")

        while not shutdown_event.is_set():
            await asyncio.wait(
                [shutdown_event.wait(), self._new_frame.wait()],
                return_when=asyncio.FIRST_COMPLETED,
            )
            if shutdown_event.is_set():
                break
            self._new_frame.clear()
            async with self._lock:
                robot_items = list(self._queues.items())
            for robot_id, queue in robot_items:
                while not queue.empty():
                    try:
                        jpeg_bytes, model_name = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    try:
                        result = await asyncio.to_thread(self._infer, jpeg_bytes, model_name)
                        self.robot_store.set_last_detection(robot_id, result)
                        await self._dispatch_result(robot_id, result)
                    except Exception as exc:
                        logger.exception("Inference failed for robot %s with model %s: %s", robot_id, model_name, exc)

    async def _dispatch_result(self, robot_id: str, result: dict) -> None:
        async with self._lock:
            callback = self._callbacks.get(robot_id)
        if not callback:
            logger.debug("No active callback for robot %s; skipping detection delivery.", robot_id)
            return
        try:
            await callback(result)
        except Exception:
            logger.exception("Failed to deliver inference result to robot %s", robot_id)

    def _infer(self, jpeg_bytes: bytes, model_name: str) -> dict:
        image = Image.open(io.BytesIO(jpeg_bytes)).convert("RGB")
        try:
            adapter = self.model_registry.get(model_name)
        except KeyError:
            adapter = self.model_registry.get(self.default_model_name)
            logger.warning(
                "Model %s not found, falling back to default model %s", model_name, self.default_model_name
            )
        return adapter.infer(image)
