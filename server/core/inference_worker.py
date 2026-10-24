import asyncio
import io
import logging
from typing import Awaitable, Callable, Dict, Optional, Tuple

import numpy as np
from PIL import Image

from .background import run_in_daemon_thread
from .model_adapters import ModelAdapter, ModelRegistry
from .robot_store import RobotStore
from .sightings import SightingStore
from .viewer_hub import ViewerHub

logger = logging.getLogger("pest_robot_server.inference_worker")
INFERENCE_TIMEOUT_SECONDS = 10.0
CALLBACK_TIMEOUT_SECONDS = 5.0


class InferenceWorker:
    """Background worker that processes frames and returns detections."""

    def __init__(
        self,
        model_registry: ModelRegistry,
        robot_store: RobotStore,
        viewer_hub: ViewerHub,
        max_queue_size: int = 2,
        default_model_name: str = "onnx",
        sightings: Optional[SightingStore] = None,
    ) -> None:
        self.model_registry = model_registry
        self.robot_store = robot_store
        self.viewer_hub = viewer_hub
        self.sightings = sightings
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

    async def unregister_callback(self, robot_id: str, callback: Callable[[dict], Awaitable[None]]) -> None:
        # Only remove our own callback: a reconnected robot may already have replaced it.
        async with self._lock:
            if self._callbacks.get(robot_id) is callback:
                del self._callbacks[robot_id]

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
                    adapter = self._get_adapter(model_name)
                    # Loading is not covered by the inference timeout: the first load takes
                    # several seconds, and timing it out would silently drop the frame.
                    await run_in_daemon_thread(adapter.ensure_loaded, name="model-load")
                    result = await asyncio.wait_for(
                        asyncio.to_thread(self._infer, jpeg_bytes, adapter),
                        timeout=INFERENCE_TIMEOUT_SECONDS,
                    )
                    await self.publish_result(robot_id, result, jpeg_bytes)
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

    async def publish_result(self, robot_id: str, result: dict, jpeg_bytes: bytes, notify_robot: bool = True) -> None:
        """Store a detection result, add it to history, show it to viewers and (optionally) the robot.

        Used for the server's own inference and for detections a robot computed itself
        (monitor mode, where the robot already has them and notify_robot is False).
        """
        await asyncio.to_thread(self.robot_store.set_last_detection, robot_id, result)
        if self.sightings is not None:
            await asyncio.to_thread(self.sightings.record, robot_id, result, jpeg_bytes)
        self.viewer_hub.publish_json(robot_id, result)
        if notify_robot:
            await self._dispatch_result(robot_id, result)

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

    def _get_adapter(self, model_name: str) -> ModelAdapter:
        try:
            return self.model_registry.get(model_name)
        except KeyError:
            logger.warning(
                "Model %s not found, falling back to default model %s", model_name, self.default_model_name
            )
            return self.model_registry.get(self.default_model_name)

    def _infer(self, jpeg_bytes: bytes, adapter: ModelAdapter) -> dict:
        image = Image.open(io.BytesIO(jpeg_bytes)).convert("RGB")
        result = adapter.infer(image)
        # The Pi reads a "detections" list shaped like its own local model output.
        result["detections"] = [
            {"class": label, "confidence": score, "bbox": box}
            for box, score, label in zip(result["boxes"], result["scores"], result["labels"])
        ]
        result["image_size"] = [image.width, image.height]
        return result
