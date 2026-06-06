import asyncio
import io
import logging
from typing import Awaitable, Callable, Dict, Optional, Tuple

import numpy as np
from PIL import Image

from .model_adapters import ModelRegistry
from .robot_store import RobotStore

logger = logging.getLogger("pest_robot_server.inference_worker")
INFERENCE_TIMEOUT_SECONDS = 10.0
CALLBACK_TIMEOUT_SECONDS = 5.0


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
        self._pending_frames: Dict[str, Tuple[bytes, str]] = {}
        self._callbacks: Dict[str, Callable[[dict], Awaitable[None]]] = {}
        self._new_frame = asyncio.Event()
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        logger.info("Inference worker ready; detection models will load on demand.")

    async def enqueue_frame(self, robot_id: str, jpeg_bytes: bytes, model_name: Optional[str] = None) -> None:
        if not model_name:
            model_name = self.default_model_name
        async with self._lock:
            previous_frame = self._pending_frames.get(robot_id)
            self._pending_frames[robot_id] = (jpeg_bytes, model_name)
            if previous_frame is not None:
                logger.debug("Coalesced older frame for robot %s", robot_id)
            self._new_frame.set()

    async def register_callback(self, robot_id: str, callback: Callable[[dict], Awaitable[None]]) -> None:
        async with self._lock:
            self._callbacks[robot_id] = callback

    async def unregister_callback(self, robot_id: str) -> None:
        async with self._lock:
            self._callbacks.pop(robot_id, None)

    async def flush_queue(self, robot_id: str) -> None:
        async with self._lock:
            self._pending_frames.pop(robot_id, None)
            if not self._pending_frames:
                self._new_frame.clear()

    async def run(self, shutdown_event: asyncio.Event) -> None:
        model_names = [model["name"] for model in self.model_registry.list_models()]
        if not model_names:
            raise RuntimeError("Inference worker has no available models")

        while not shutdown_event.is_set():
            shutdown_task = asyncio.create_task(shutdown_event.wait())
            frame_task = asyncio.create_task(self._new_frame.wait())
            done, pending = await asyncio.wait(
                {shutdown_task, frame_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            if shutdown_event.is_set():
                break
            self._new_frame.clear()
            if frame_task in done and frame_task.cancelled():
                continue
            async with self._lock:
                pending_items = list(self._pending_frames.items())
                self._pending_frames.clear()

            for robot_id, (jpeg_bytes, model_name) in pending_items:
                try:
                    result = await asyncio.wait_for(
                        asyncio.to_thread(self._infer, jpeg_bytes, model_name),
                        timeout=INFERENCE_TIMEOUT_SECONDS,
                    )
                    await asyncio.to_thread(self.robot_store.set_last_detection, robot_id, result)
                    await self._dispatch_result(robot_id, result)
                except asyncio.TimeoutError:
                    logger.warning(
                        "Inference timed out for robot %s with model %s after %.1f seconds",
                        robot_id,
                        model_name,
                        INFERENCE_TIMEOUT_SECONDS,
                    )
                except Exception as exc:
                    logger.exception("Inference failed for robot %s with model %s: %s", robot_id, model_name, exc)

            async with self._lock:
                if self._pending_frames:
                    self._new_frame.set()

    async def _dispatch_result(self, robot_id: str, result: dict) -> None:
        async with self._lock:
            callback = self._callbacks.get(robot_id)
        if not callback:
            logger.debug("No active callback for robot %s; skipping detection delivery.", robot_id)
            return
        try:
            await asyncio.wait_for(callback(result), timeout=CALLBACK_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            logger.warning(
                "Detection callback timed out for robot %s after %.1f seconds",
                robot_id,
                CALLBACK_TIMEOUT_SECONDS,
            )
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

        if not adapter.is_loaded():
            adapter.load()

        return adapter.infer(image)
