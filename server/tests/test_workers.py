"""The inference worker and viewer hub on their own, without a server."""

import asyncio

from conftest import FakeAdapter, make_jpeg
from core.inference_worker import InferenceWorker
from core.model_adapters import ModelRegistry
from core.viewer_hub import _Viewer


class StoreStub:
    def __init__(self) -> None:
        self.detections = []

    def set_last_detection(self, robot_id, detection):
        self.detections.append((robot_id, detection))


class HubStub:
    def __init__(self) -> None:
        self.published = []

    def publish_json(self, robot_id, payload):
        self.published.append((robot_id, payload))


def make_worker(tmp_path):
    adapter = FakeAdapter(tmp_path / "fake.pt")
    registry = ModelRegistry(tmp_path)
    registry.register("fake", adapter)
    worker = InferenceWorker(registry, StoreStub(), HubStub(), default_model_name="fake")
    return worker, adapter


async def run_worker_until(worker, condition, timeout=5.0):
    shutdown = asyncio.Event()
    task = asyncio.create_task(worker.run(shutdown))
    try:
        async with asyncio.timeout(timeout):
            while not condition():
                await asyncio.sleep(0.01)
    finally:
        shutdown.set()
        await task


def test_worker_only_processes_the_newest_frame(tmp_path):
    async def scenario():
        worker, adapter = make_worker(tmp_path)
        # Three frames arrive before the worker gets to them: only the last is worth processing.
        for size in (100, 200, 300):
            await worker.enqueue_frame("r1", make_jpeg(size, size), model_name="fake")
        await run_worker_until(worker, lambda: adapter.infer_calls >= 1)
        await asyncio.sleep(0.1)
        return worker, adapter

    worker, adapter = asyncio.run(scenario())
    assert adapter.infer_calls == 1
    assert worker.robot_store.detections[0][1]["image_size"] == [300, 300]


def test_worker_sends_results_to_robot_and_viewers(tmp_path):
    received = []

    async def scenario():
        worker, _ = make_worker(tmp_path)

        async def callback(result):
            received.append(result)

        await worker.register_callback("r1", callback)
        await worker.enqueue_frame("r1", make_jpeg())
        await run_worker_until(worker, lambda: received)
        return worker

    worker = asyncio.run(scenario())
    assert received[0]["labels"] == ["whitefly"]
    assert worker.viewer_hub.published[0][0] == "r1"


def test_a_stale_connection_cannot_remove_the_new_callback(tmp_path):
    async def scenario():
        worker, _ = make_worker(tmp_path)

        async def old_callback(result):
            pass

        async def new_callback(result):
            pass

        await worker.register_callback("r1", old_callback)
        await worker.register_callback("r1", new_callback)  # robot reconnected
        await worker.unregister_callback("r1", old_callback)  # old socket finally closes
        return worker._callbacks.get("r1"), new_callback

    current, new_callback = asyncio.run(scenario())
    assert current is new_callback


class SocketStub:
    def __init__(self) -> None:
        self.sent = []

    async def send_bytes(self, data):
        self.sent.append(("bytes", data))

    async def send_json(self, data):
        self.sent.append(("json", data))


def test_slow_viewer_gets_only_the_newest_frame_and_detection():
    async def scenario():
        socket = SocketStub()
        viewer = _Viewer(socket)
        # Everything below arrives while the viewer is still busy sending.
        viewer.offer(b"frame-1")
        viewer.offer({"labels": ["old"]})
        viewer.offer(b"frame-2")
        viewer.offer(b"frame-3")
        viewer.offer({"labels": ["new"]})
        sender = asyncio.create_task(viewer.run())
        await asyncio.sleep(0.05)
        sender.cancel()
        return socket.sent

    assert asyncio.run(scenario()) == [("json", {"labels": ["new"]}), ("bytes", b"frame-3")]
