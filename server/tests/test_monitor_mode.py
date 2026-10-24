"""Monitor mode: the robot runs its own model and the server only stores and relays."""

import json

import pytest

from conftest import KEY_HEADERS, get_robot, make_jpeg, wait_until
from routers.stream import parse_robot_detections

MONITOR_URL = "/ws/stream/robot-1?mode=monitor"
BOX = [12.0, 34.0, 56.0, 78.0]


def detections_message(*items, size=(320, 240)):
    return json.dumps({
        "type": "detections",
        "image_size": list(size),
        "detections": [{"class": label, "confidence": conf, "bbox": BOX} for label, conf in items],
    })


def receive_until_both(viewer):
    """Collect one frame and one detection message from a viewer socket."""
    frame, detection = None, None
    while frame is None or detection is None:
        message = viewer.receive()
        if message.get("bytes") is not None:
            frame = message["bytes"]
        elif message.get("text") is not None:
            detection = json.loads(message["text"])
    return frame, detection


# --- Parsing what the robot sends ------------------------------------------------------


def test_robot_detections_become_the_server_result_format():
    result = parse_robot_detections(json.loads(detections_message(("whitefly", 0.8))))
    assert result["boxes"] == [BOX]
    assert result["labels"] == ["whitefly"]
    assert result["scores"] == [0.8]
    assert result["image_size"] == [320, 240]
    assert result["detections"] == [{"class": "whitefly", "confidence": 0.8, "bbox": BOX}]


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "status"},
        {"type": "detections", "image_size": [320, 240]},
        {"type": "detections", "image_size": [0, 240], "detections": []},
        {"type": "detections", "image_size": [320, 240], "detections": [{"class": "x", "confidence": 0.5}]},
        {"type": "detections", "image_size": [320, 240], "detections": [{"class": "x", "confidence": "high", "bbox": BOX}]},
        {"type": "detections", "image_size": [320, 240], "detections": [{"class": "x", "confidence": 0.5, "bbox": [1, 2]}]},
        {"type": "detections", "image_size": [320, 240], "detections": [{"class": "x", "confidence": 0.5, "bbox": BOX}] * 101},
        ["not", "a", "dict"],
    ],
    ids=["wrong-type", "no-list", "bad-size", "no-bbox", "bad-confidence", "short-bbox", "too-many", "not-dict"],
)
def test_malformed_robot_detections_are_rejected(payload):
    assert parse_robot_detections(payload) is None


# --- Through the server -----------------------------------------------------------------


def test_monitor_mode_relays_frames_and_robot_detections_without_server_inference(client, fake_adapter):
    frame = make_jpeg()
    with client.websocket_connect("/ws/view/robot-1") as viewer:
        with client.websocket_connect(MONITOR_URL, headers=KEY_HEADERS) as robot:
            robot.send_text(detections_message(("mealy bug", 0.9)))
            robot.send_bytes(frame)
            got_frame, got_detection = receive_until_both(viewer)

    assert got_frame == frame
    assert got_detection["labels"] == ["mealy bug"]
    assert fake_adapter.infer_calls == 0  # the server ran no model


def test_monitor_mode_detections_go_into_history_with_their_frame(client):
    frame = make_jpeg()
    with client.websocket_connect(MONITOR_URL, headers=KEY_HEADERS) as robot:
        robot.send_text(detections_message(("mealy bug", 0.9)))
        robot.send_bytes(frame)
        assert wait_until(lambda: client.get("/api/sightings").json() != [])

    [sighting] = client.get("/api/sightings").json()
    assert sighting["label"] == "mealy bug" and sighting["boxes"] == [BOX]
    assert client.get(sighting["snapshot_url"]).content == frame


def test_frames_without_detections_are_only_relayed(client):
    with client.websocket_connect("/ws/view/robot-1") as viewer:
        with client.websocket_connect(MONITOR_URL, headers=KEY_HEADERS) as robot:
            robot.send_bytes(make_jpeg())
            assert viewer.receive().get("bytes")
    assert client.get("/api/sightings").json() == []


def test_a_malformed_message_is_skipped_and_the_robot_stays_connected(client):
    with client.websocket_connect(MONITOR_URL, headers=KEY_HEADERS) as robot:
        robot.send_text("{not json")
        robot.send_text(json.dumps({"type": "detections", "detections": "nope"}))
        robot.send_bytes(make_jpeg())  # must not be paired with the bad messages
        robot.send_text(detections_message(("whitefly", 0.7)))
        robot.send_bytes(make_jpeg())
        assert wait_until(lambda: len(client.get("/api/sightings").json()) == 1)
    assert client.get("/api/sightings").json()[0]["label"] == "whitefly"


def test_monitor_mode_sends_nothing_back_to_the_robot(client, monkeypatch):
    # The robot already has its own results; echoing them back would waste the Pi's bandwidth.
    worker = client.app.state.inference_worker
    sent_to_robot = []

    async def record_dispatch(robot_id, result):
        sent_to_robot.append(result)

    monkeypatch.setattr(worker, "_dispatch_result", record_dispatch)
    with client.websocket_connect(MONITOR_URL, headers=KEY_HEADERS) as robot:
        robot.send_text(detections_message(("whitefly", 0.7)))
        robot.send_bytes(make_jpeg())
        assert wait_until(lambda: client.get("/api/sightings").json() != [])
    assert sent_to_robot == []


def test_robot_api_reports_where_detection_runs(client):
    with client.websocket_connect(MONITOR_URL, headers=KEY_HEADERS):
        assert wait_until(lambda: (get_robot(client, "robot-1") or {}).get("detection_mode") == "robot")
    assert wait_until(lambda: get_robot(client, "robot-1")["detection_mode"] is None)

    with client.websocket_connect("/ws/stream/robot-1?model=fake", headers=KEY_HEADERS):
        assert wait_until(lambda: get_robot(client, "robot-1")["detection_mode"] == "server")


def test_monitor_mode_requires_the_robot_key(client):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(MONITOR_URL):
            pass
