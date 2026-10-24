"""Shared fixtures: a fake model, a throwaway database and a known robot key.

The real RF-DETR model takes seconds to load and needs the 121 MB weights file,
so the tests use FakeAdapter, which returns one fixed detection instantly.
"""

import io
import time
from pathlib import Path
from typing import Callable

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from core.model_adapters import ModelAdapter, ModelRegistry
from main import create_app

ROBOT_KEY = "test-robot-key"
KEY_HEADERS = {"X-Robot-Key": ROBOT_KEY}
FAKE_BOX = [10.0, 20.0, 110.0, 120.0]


class FakeAdapter(ModelAdapter):
    """Stands in for RF-DETR: always detects one whitefly."""

    def __init__(self, model_path: Path, load_delay: float = 0.0) -> None:
        super().__init__(model_path, labels=["background", "whitefly"])
        self.architecture = "fake"
        self.infer_calls = 0
        self.load_calls = 0
        # Simulates the real model's multi-second load, to expose loading races.
        self.load_delay = load_delay

    def load(self) -> None:
        self.load_calls += 1
        time.sleep(self.load_delay)
        self._loaded = True

    def infer(self, image: Image.Image) -> dict:
        self.infer_calls += 1
        return {"boxes": [list(FAKE_BOX)], "scores": [0.9], "labels": ["whitefly"]}


@pytest.fixture(autouse=True)
def robot_key(monkeypatch):
    # Overrides whatever server/.env set, so tests never depend on the real key.
    monkeypatch.setenv("ROBOT_KEY", ROBOT_KEY)
    return ROBOT_KEY


@pytest.fixture
def fake_adapter(tmp_path) -> FakeAdapter:
    # The ".pt" suffix makes it the server's default model, like the real one.
    return FakeAdapter(tmp_path / "fake.pt")


@pytest.fixture
def client(tmp_path, fake_adapter):
    registry = ModelRegistry(tmp_path)
    registry.register("fake", fake_adapter)
    app = create_app(model_registry=registry, db_url=f"sqlite:///{tmp_path / 'test.db'}", data_dir=tmp_path / "data")
    # Using TestClient as a context manager runs the app's startup and shutdown.
    with TestClient(app) as test_client:
        yield test_client


def make_jpeg(width: int = 320, height: int = 240) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (40, 120, 40)).save(buffer, "JPEG")
    return buffer.getvalue()


def get_robot(client: TestClient, robot_id: str):
    response = client.get(f"/api/robots/{robot_id}")
    return response.json() if response.status_code == 200 else None


def wait_until(condition: Callable[[], bool], timeout: float = 3.0) -> bool:
    """Poll until condition() is true. Socket handlers update the database asynchronously."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return condition()
