"""The model loads exactly once, and frames that arrive while it loads are not dropped."""

import asyncio
import threading

from fastapi.testclient import TestClient

import core.inference_worker as inference_worker
from conftest import KEY_HEADERS, FakeAdapter, make_jpeg
from core.model_adapters import ModelRegistry
from main import create_app


def test_concurrent_callers_load_the_model_once(tmp_path):
    adapter = FakeAdapter(tmp_path / "fake.pt", load_delay=0.3)
    threads = [threading.Thread(target=adapter.ensure_loaded) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert adapter.load_calls == 1
    assert adapter.is_loaded()


def test_a_failed_load_can_be_retried(tmp_path):
    adapter = FakeAdapter(tmp_path / "fake.pt")
    original_load = adapter.load
    attempts = []

    def flaky_load():
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("disk not ready")
        original_load()

    adapter.load = flaky_load
    try:
        adapter.ensure_loaded()
    except RuntimeError:
        pass
    adapter.ensure_loaded()
    assert adapter.is_loaded() and len(attempts) == 2


def test_frame_sent_during_startup_preload_gets_a_result(tmp_path, monkeypatch):
    # Loading takes longer than the inference timeout, like the real model on a slow machine.
    monkeypatch.setattr(inference_worker, "INFERENCE_TIMEOUT_SECONDS", 0.2)
    adapter = FakeAdapter(tmp_path / "fake.pt", load_delay=0.6)
    registry = ModelRegistry(tmp_path)
    registry.register("fake", adapter)
    app = create_app(model_registry=registry, db_url=f"sqlite:///{tmp_path / 'test.db'}", data_dir=tmp_path / "data")

    with TestClient(app) as client:
        # The background preload has just started; send a frame straight away.
        with client.websocket_connect("/ws/stream/robot-1?model=fake", headers=KEY_HEADERS) as stream:
            stream.send_bytes(make_jpeg())
            assert stream.receive_json()["labels"] == ["whitefly"]

    assert adapter.load_calls == 1


def test_worker_waits_for_a_slow_load_instead_of_dropping_the_frame(tmp_path, monkeypatch):
    monkeypatch.setattr(inference_worker, "INFERENCE_TIMEOUT_SECONDS", 0.2)
    adapter = FakeAdapter(tmp_path / "fake.pt", load_delay=0.6)
    registry = ModelRegistry(tmp_path)
    registry.register("fake", adapter)

    class Store:
        def set_last_detection(self, robot_id, detection):
            pass

    class Hub:
        def publish_json(self, robot_id, payload):
            pass

    received = []

    async def scenario():
        worker = inference_worker.InferenceWorker(registry, Store(), Hub(), default_model_name="fake")

        async def callback(result):
            received.append(result)

        await worker.register_callback("r1", callback)
        await worker.enqueue_frame("r1", make_jpeg(), model_name="fake")
        shutdown = asyncio.Event()
        task = asyncio.create_task(worker.run(shutdown))
        async with asyncio.timeout(5):
            while not received:
                await asyncio.sleep(0.02)
        shutdown.set()
        await task

    asyncio.run(scenario())
    assert received[0]["labels"] == ["whitefly"]
    assert adapter.load_calls == 1
