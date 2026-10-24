"""Detection history: how detections become sightings, and the history API."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from conftest import FAKE_BOX, KEY_HEADERS, make_jpeg, wait_until
from core.sightings import SightingStore

START = datetime(2026, 6, 1, 8, 0, tzinfo=UTC)


class FakeClock:
    """Lets a test move time forward instantly."""

    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def result(*hits):
    """Build an inference result from (label, confidence) pairs."""
    return {
        "boxes": [[10.0 * i, 10.0, 10.0 * i + 50, 60.0] for i, _ in enumerate(hits)],
        "scores": [confidence for _, confidence in hits],
        "labels": [label for label, _ in hits],
        "image_size": [320, 240],
    }


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def store(tmp_path, clock):
    sightings = SightingStore(f"sqlite:///{tmp_path / 'h.db'}", tmp_path / "snapshots", clock=clock)
    yield sightings
    sightings.close()


def photo(text: str) -> bytes:
    return text.encode()  # the store treats photos as opaque bytes


# --- Grouping detections into sightings ---------------------------------------------


def test_first_detection_creates_a_sighting_with_photo(store):
    store.record("r1", result(("whitefly", 0.7)), photo("frame-1"))
    [sighting] = store.list()
    assert (sighting.robot_id, sighting.label, sighting.frames) == ("r1", "whitefly", 1)
    assert sighting.first_seen == START
    assert store.snapshot_path(sighting.id).read_bytes() == b"frame-1"


def test_empty_results_create_nothing(store):
    store.record("r1", result(), photo("frame"))
    assert store.list() == []


def test_same_pest_within_the_gap_extends_the_sighting(store, clock):
    store.record("r1", result(("whitefly", 0.7)), photo("frame-1"))
    for _ in range(4):
        clock.advance(10)  # each frame is within 30 s of the previous one
        store.record("r1", result(("whitefly", 0.6)), photo("later"))
    store.flush()
    [sighting] = store.list()
    assert sighting.frames == 5
    assert sighting.last_seen == START + timedelta(seconds=40)


def test_pest_returning_after_the_gap_is_a_new_sighting(store, clock):
    store.record("r1", result(("whitefly", 0.7)), photo("a"))
    clock.advance(31)
    store.record("r1", result(("whitefly", 0.7)), photo("b"))
    assert len(store.list()) == 2


def test_each_pest_type_and_robot_gets_its_own_sighting(store):
    store.record("r1", result(("whitefly", 0.7), ("mealy bug", 0.8)), photo("a"))
    store.record("r2", result(("whitefly", 0.9)), photo("b"))
    assert sorted((s.robot_id, s.label) for s in store.list()) == [
        ("r1", "mealy bug"),
        ("r1", "whitefly"),
        ("r2", "whitefly"),
    ]


def test_several_of_the_same_pest_in_one_frame_is_one_sighting(store):
    store.record("r1", result(("whitefly", 0.6), ("whitefly", 0.9)), photo("a"))
    [sighting] = store.list()
    assert sighting.best_confidence == pytest.approx(0.9)
    assert len(json.loads(sighting.boxes)) == 2  # both whiteflies are boxed in the photo


def test_photo_is_replaced_by_a_more_confident_frame(store, clock):
    store.record("r1", result(("whitefly", 0.6)), photo("blurry"))
    clock.advance(2)
    store.record("r1", result(("whitefly", 0.95)), photo("sharp"))
    clock.advance(2)
    store.record("r1", result(("whitefly", 0.7)), photo("worse"))
    store.flush()
    [sighting] = store.list()
    assert sighting.best_confidence == pytest.approx(0.95)
    assert store.snapshot_path(sighting.id).read_bytes() == b"sharp"


# --- Few disk writes ----------------------------------------------------------------


def test_updates_reach_the_database_at_most_every_five_seconds(store, clock):
    store.record("r1", result(("whitefly", 0.7)), photo("a"))
    clock.advance(1)
    store.record("r1", result(("whitefly", 0.7)), photo("a"))
    assert store.list()[0].frames == 1  # still only in memory
    clock.advance(5)
    store.record("r1", result(("whitefly", 0.7)), photo("a"))
    assert store.list()[0].frames == 3


def test_flush_due_saves_and_closes_finished_sightings(store, clock):
    store.record("r1", result(("whitefly", 0.7)), photo("a"))
    clock.advance(1)
    store.record("r1", result(("whitefly", 0.7)), photo("a"))
    clock.advance(40)  # the pest is gone; no more frames arrive
    store.flush_due()
    assert store.list()[0].frames == 2
    clock.advance(1)
    store.record("r1", result(("whitefly", 0.7)), photo("a"))
    assert len(store.list()) == 2  # it was closed, so this is a new sighting


# --- Reading -----------------------------------------------------------------------


def test_list_filters_and_pages_newest_first(store, clock):
    for i in range(5):
        store.record("r1", result(("whitefly", 0.7)), photo("a"))
        clock.advance(31)
    store.record("r2", result(("mealy bug", 0.7)), photo("b"))

    assert [s.robot_id for s in store.list(limit=2)] == ["r2", "r1"]
    first_page = store.list(robot_id="r1", limit=3)
    second_page = store.list(robot_id="r1", limit=3, before_id=first_page[-1].id)
    assert len(first_page) == 3 and len(second_page) == 2
    assert all(a.id > b.id for a, b in zip(first_page, first_page[1:]))
    assert [s.label for s in store.list(label="mealy bug")] == ["mealy bug"]
    assert len(store.list(since=START + timedelta(seconds=31 * 4))) == 2


def test_summary_counts_sightings_per_pest(store, clock):
    for label in ["whitefly", "whitefly", "mealy bug"]:
        store.record("r1", result((label, 0.7)), photo("a"))
        clock.advance(31)
    summary = store.summary()
    assert [(row["label"], row["count"]) for row in summary] == [("whitefly", 2), ("mealy bug", 1)]
    assert summary[0]["last_seen"].utcoffset() == timedelta(0)


# --- Through the server ------------------------------------------------------------


def test_streaming_records_sightings_available_through_the_api(client):
    with client.websocket_connect("/ws/stream/robot-1?model=fake", headers=KEY_HEADERS) as stream:
        stream.send_bytes(make_jpeg())
        stream.receive_json()

    assert wait_until(lambda: client.get("/api/sightings").json() != [])
    [sighting] = client.get("/api/sightings").json()
    assert sighting["robot_id"] == "robot-1" and sighting["label"] == "whitefly"
    assert sighting["boxes"] == [FAKE_BOX]
    assert (sighting["image_width"], sighting["image_height"]) == (320, 240)

    snapshot = client.get(sighting["snapshot_url"])
    assert snapshot.status_code == 200
    assert snapshot.headers["content-type"] == "image/jpeg"
    assert snapshot.content[:2] == b"\xff\xd8"  # JPEG signature

    assert client.get(f"/api/sightings/{sighting['id']}").json()["label"] == "whitefly"
    summary = client.get("/api/sightings/summary").json()
    assert [(row["label"], row["count"]) for row in summary] == [("whitefly", 1)]


def test_api_filters_by_robot(client):
    with client.websocket_connect("/ws/stream/robot-1?model=fake", headers=KEY_HEADERS) as stream:
        stream.send_bytes(make_jpeg())
        stream.receive_json()
    assert wait_until(lambda: client.get("/api/sightings").json() != [])
    assert client.get("/api/sightings", params={"robot_id": "other"}).json() == []
    assert len(client.get("/api/sightings", params={"robot_id": "robot-1"}).json()) == 1


def test_missing_sighting_and_snapshot_are_404(client):
    assert client.get("/api/sightings/999").status_code == 404
    assert client.get("/api/sightings/999/snapshot").status_code == 404


# --- Deleting robots ----------------------------------------------------------------


def test_robot_can_be_deleted_and_history_is_kept(client):
    with client.websocket_connect("/ws/stream/robot-1?model=fake", headers=KEY_HEADERS) as stream:
        stream.send_bytes(make_jpeg())
        stream.receive_json()
    assert wait_until(lambda: client.get("/api/robots/robot-1").status_code == 200)
    assert wait_until(lambda: "robot-1" not in client.app.state.stream_connections)

    assert client.delete("/api/robots/robot-1").status_code == 200
    assert client.get("/api/robots/robot-1").status_code == 404
    assert len(client.get("/api/sightings").json()) == 1


def test_connected_robot_cannot_be_deleted(client):
    with client.websocket_connect("/ws/control/robot-1", headers=KEY_HEADERS):
        assert wait_until(lambda: client.get("/api/robots/robot-1").status_code == 200)
        assert client.delete("/api/robots/robot-1").status_code == 409


def test_deleting_an_unknown_robot_is_404(client):
    assert client.delete("/api/robots/nope").status_code == 404
