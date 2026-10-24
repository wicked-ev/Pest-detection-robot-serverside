"""Detections are kept current in memory but written to SQLite sparingly."""

import json
import time
from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from core.robot_store import RobotStore

PEST = {"boxes": [[1, 2, 3, 4]], "scores": [0.9], "labels": ["whitefly"]}
OTHER_PEST = {"boxes": [[5, 6, 7, 8]], "scores": [0.8], "labels": ["mealy bug"]}
NOTHING = {"boxes": [], "scores": [], "labels": []}


@pytest.fixture
def stores():
    """Collects every store a test opens and closes them afterwards."""
    opened = []
    yield opened
    for store in opened:
        store.close()


@pytest.fixture(autouse=True)
def _track_stores(stores, monkeypatch):
    original_init = RobotStore.__init__

    def tracking_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        stores.append(self)

    monkeypatch.setattr(RobotStore, "__init__", tracking_init)


def make_store(tmp_path, interval: float = 60.0) -> RobotStore:
    store = RobotStore(db_url=f"sqlite:///{tmp_path / 'robots.db'}", detection_persist_interval=interval)
    store.ensure_robot("r1")
    return store


def labels_in_memory(store: RobotStore):
    return json.loads(store.get_robot("r1").last_detection)["labels"]


def labels_on_disk(tmp_path):
    # A fresh store reads only what was actually written to the database.
    record = RobotStore(db_url=f"sqlite:///{tmp_path / 'robots.db'}").get_robot("r1")
    return json.loads(record.last_detection)["labels"] if record.last_detection else None


def test_empty_results_are_not_stored(tmp_path):
    store = make_store(tmp_path)
    store.set_last_detection("r1", NOTHING)
    assert store.get_robot("r1").last_detection is None
    assert labels_on_disk(tmp_path) is None


def test_empty_results_do_not_hide_the_last_pest_found(tmp_path):
    store = make_store(tmp_path)
    store.set_last_detection("r1", PEST)
    store.set_last_detection("r1", NOTHING)
    assert labels_in_memory(store) == ["whitefly"]


def test_first_detection_is_written_immediately(tmp_path):
    store = make_store(tmp_path)
    store.set_last_detection("r1", PEST)
    assert labels_on_disk(tmp_path) == ["whitefly"]


def test_rapid_detections_update_memory_but_not_disk(tmp_path):
    store = make_store(tmp_path, interval=60.0)
    store.set_last_detection("r1", PEST)
    for _ in range(20):
        store.set_last_detection("r1", OTHER_PEST)
    # The API (memory) shows the newest result; the disk still has the first write.
    assert labels_in_memory(store) == ["mealy bug"]
    assert labels_on_disk(tmp_path) == ["whitefly"]


def test_disk_catches_up_after_the_interval(tmp_path):
    store = make_store(tmp_path, interval=0.2)
    store.set_last_detection("r1", PEST)
    store.set_last_detection("r1", OTHER_PEST)
    time.sleep(0.25)
    store.set_last_detection("r1", OTHER_PEST)
    assert labels_on_disk(tmp_path) == ["mealy bug"]


def test_status_updates_keep_and_save_the_latest_detection(tmp_path):
    store = make_store(tmp_path, interval=60.0)
    store.set_last_detection("r1", PEST)
    store.set_last_detection("r1", OTHER_PEST)  # pending, not on disk yet
    store.update_status("r1", status="online")  # e.g. a heartbeat
    assert labels_in_memory(store) == ["mealy bug"]  # not reverted to the older disk value
    assert labels_on_disk(tmp_path) == ["mealy bug"]  # saved along with the status


def test_streaming_updates_keep_the_latest_detection(tmp_path):
    store = make_store(tmp_path, interval=60.0)
    store.set_last_detection("r1", PEST)
    store.set_last_detection("r1", OTHER_PEST)
    store.set_streaming("r1", False)
    assert labels_in_memory(store) == ["mealy bug"]


def test_flush_saves_pending_detections(tmp_path):
    store = make_store(tmp_path, interval=60.0)
    store.set_last_detection("r1", PEST)
    store.set_last_detection("r1", OTHER_PEST)
    store.flush()
    assert labels_on_disk(tmp_path) == ["mealy bug"]


def test_detections_for_unknown_robots_are_ignored(tmp_path):
    store = make_store(tmp_path)
    store.set_last_detection("ghost", PEST)
    assert store.get_robot("ghost") is None


def test_server_shutdown_flushes_pending_detections(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from conftest import FakeAdapter
    from core.model_adapters import ModelRegistry
    from main import create_app

    flushed = []
    original_flush = RobotStore.flush
    monkeypatch.setattr(RobotStore, "flush", lambda self: (flushed.append(True), original_flush(self)))
    registry = ModelRegistry(tmp_path)
    registry.register("fake", FakeAdapter(tmp_path / "fake.pt"))
    with TestClient(create_app(model_registry=registry, db_url=f"sqlite:///{tmp_path / 'app.db'}", data_dir=tmp_path / "data")):
        assert flushed == []
    assert flushed == [True]


def test_startup_clears_status_left_over_from_a_previous_run(tmp_path):
    store = make_store(tmp_path)
    store.update_status("r1", status="online")
    store.set_streaming("r1", True)
    store.set_last_detection("r1", PEST)
    # The server stopped without cleaning up; a new run starts on the same database.
    restarted = RobotStore(db_url=f"sqlite:///{tmp_path / 'robots.db'}")
    restarted.mark_all_disconnected()
    robot = restarted.get_robot("r1")
    assert robot.status == "offline" and robot.streaming is False
    assert json.loads(robot.last_detection)["labels"] == ["whitefly"]  # history is kept


def test_timestamps_come_back_as_utc(tmp_path):
    store = make_store(tmp_path)
    store.update_status("r1", status="online")
    reopened = RobotStore(db_url=f"sqlite:///{tmp_path / 'robots.db'}")
    last_seen = reopened.get_robot("r1").last_seen
    assert last_seen.utcoffset() == timedelta(0)
    assert abs(datetime.now(UTC) - last_seen) < timedelta(minutes=1)


def test_other_timezones_are_converted_to_utc(tmp_path):
    store = make_store(tmp_path)
    plus_two = timezone(timedelta(hours=2))
    store.update_status("r1", status="online", last_seen=datetime(2026, 6, 1, 14, 0, tzinfo=plus_two))
    reopened = RobotStore(db_url=f"sqlite:///{tmp_path / 'robots.db'}")
    assert reopened.get_robot("r1").last_seen == datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def test_naive_timestamps_are_rejected(tmp_path):
    # A naive datetime has no timezone, so it is ambiguous; refusing it prevents the old bug.
    store = make_store(tmp_path)
    with pytest.raises(Exception, match="timezone-aware"):
        store.update_status("r1", status="online", last_seen=datetime(2026, 6, 1, 12, 0))


def test_rows_written_before_this_change_are_read_as_utc(tmp_path):
    store = make_store(tmp_path)
    # Older versions stored naive UTC text like this.
    with store._engine.begin() as connection:
        connection.execute(text("UPDATE robotrecord SET last_seen = '2026-06-01 12:00:00.000000' WHERE robot_id = 'r1'"))
    reopened = RobotStore(db_url=f"sqlite:///{tmp_path / 'robots.db'}")
    assert reopened.get_robot("r1").last_seen == datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
