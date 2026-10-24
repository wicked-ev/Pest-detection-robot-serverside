"""How robots and dashboards connect: auth, status, commands, streaming and viewing."""

from datetime import datetime, timedelta

import pytest
from starlette.websockets import WebSocketDisconnect

import routers.control as control
from conftest import FAKE_BOX, KEY_HEADERS, get_robot, make_jpeg, wait_until

ROBOT = "robot-1"


# --- REST basics -----------------------------------------------------------


def test_health_lists_models(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert [m["name"] for m in body["models"]] == ["fake"]


def test_register_returns_robot_without_token(client):
    response = client.post("/api/robots/register", json={"robot_id": ROBOT, "name": "Field 1", "ip_address": "10.0.0.5"})
    assert response.status_code == 200
    body = response.json()
    assert body["robot_id"] == ROBOT and body["name"] == "Field 1"
    assert "token" not in body


def test_last_seen_is_sent_with_its_utc_offset(client):
    client.post("/api/robots/register", json={"robot_id": ROBOT, "name": "R", "ip_address": "1.2.3.4"})
    # Without an offset, browsers read the time as local and show it hours off.
    last_seen = datetime.fromisoformat(get_robot(client, ROBOT)["last_seen"])  # e.g. "...Z"
    assert last_seen.utcoffset() == timedelta(0)


def test_unknown_robot_is_404(client):
    assert client.get("/api/robots/nope").status_code == 404


def test_wifi_endpoint_was_removed(client):
    response = client.post(f"/api/robots/{ROBOT}/wifi", json={"ssid": "a", "password": "b"})
    assert response.status_code == 404


# --- Robot key ---------------------------------------------------------------


@pytest.mark.parametrize("path", ["/ws/control/robot-1", "/ws/stream/robot-1"])
@pytest.mark.parametrize("headers", [{}, {"X-Robot-Key": "wrong"}], ids=["no-key", "wrong-key"])
def test_robot_sockets_reject_missing_or_wrong_key(client, path, headers):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(path, headers=headers):
            pass
    assert get_robot(client, ROBOT) is None


def test_key_check_is_off_when_no_key_is_configured(client, monkeypatch):
    monkeypatch.setenv("ROBOT_KEY", "")
    with client.websocket_connect(f"/ws/control/{ROBOT}"):
        assert wait_until(lambda: get_robot(client, ROBOT) is not None)


def test_viewer_socket_needs_no_key(client):
    with client.websocket_connect(f"/ws/view/{ROBOT}"):
        pass


# --- Control socket: registration, status, commands ---------------------------


def test_robot_registers_itself_on_connect(client):
    with client.websocket_connect(f"/ws/control/{ROBOT}", headers=KEY_HEADERS):
        assert wait_until(lambda: get_robot(client, ROBOT) is not None)
        assert get_robot(client, ROBOT)["name"] == ROBOT


def test_heartbeat_marks_online_and_disconnect_marks_offline(client):
    with client.websocket_connect(f"/ws/control/{ROBOT}", headers=KEY_HEADERS) as ws:
        ws.send_json({"type": "heartbeat", "state": "READY"})
        assert wait_until(lambda: get_robot(client, ROBOT)["status"] == "online")
    assert wait_until(lambda: get_robot(client, ROBOT)["status"] == "offline")


def test_missing_heartbeats_close_the_socket(client, monkeypatch):
    monkeypatch.setattr(control, "HEARTBEAT_TIMEOUT_SECONDS", 0.3)
    with client.websocket_connect(f"/ws/control/{ROBOT}", headers=KEY_HEADERS) as ws:
        ws.send_json({"type": "heartbeat"})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    assert wait_until(lambda: get_robot(client, ROBOT)["status"] == "offline")


@pytest.mark.parametrize("command", ["start_stream", "stop_stream", "halt", "reboot", "shutdown"])
def test_commands_are_delivered_to_the_robot(client, command):
    with client.websocket_connect(f"/ws/control/{ROBOT}", headers=KEY_HEADERS) as ws:
        assert wait_until(lambda: get_robot(client, ROBOT) is not None)
        response = client.post(f"/api/robots/{ROBOT}/command", json={"command": command})
        assert response.status_code == 200
        assert ws.receive_json() == {"command": command}


def test_ambiguous_stop_command_is_rejected(client):
    # The Pi treats "stop" as a full shutdown; the dashboard must say "halt" or "shutdown".
    with client.websocket_connect(f"/ws/control/{ROBOT}", headers=KEY_HEADERS):
        assert wait_until(lambda: get_robot(client, ROBOT) is not None)
        assert client.post(f"/api/robots/{ROBOT}/command", json={"command": "stop"}).status_code == 400


def test_commands_are_refused_while_robot_is_disconnected(client):
    client.post("/api/robots/register", json={"robot_id": ROBOT, "name": "R", "ip_address": "1.2.3.4"})
    response = client.post(f"/api/robots/{ROBOT}/command", json={"command": "reboot"})
    assert response.status_code == 409


def test_reconnect_replaces_the_old_socket_and_keeps_robot_online(client):
    with client.websocket_connect(f"/ws/control/{ROBOT}", headers=KEY_HEADERS) as old:
        old.send_json({"type": "heartbeat"})
        assert wait_until(lambda: get_robot(client, ROBOT)["status"] == "online")

        with client.websocket_connect(f"/ws/control/{ROBOT}", headers=KEY_HEADERS) as new:
            new.send_json({"type": "heartbeat"})
            # The server closes the stale socket...
            with pytest.raises(WebSocketDisconnect):
                old.receive_json()
            # ...and that must not mark the reconnected robot offline.
            assert not wait_until(lambda: get_robot(client, ROBOT)["status"] == "offline", timeout=0.5)

            client.post(f"/api/robots/{ROBOT}/command", json={"command": "halt"})
            assert new.receive_json() == {"command": "halt"}


def test_reregistering_a_connected_robot_keeps_it_online(client):
    with client.websocket_connect(f"/ws/control/{ROBOT}", headers=KEY_HEADERS) as ws:
        ws.send_json({"type": "heartbeat"})
        assert wait_until(lambda: get_robot(client, ROBOT)["status"] == "online")
        client.post("/api/robots/register", json={"robot_id": ROBOT, "name": "Renamed", "ip_address": "1.2.3.4"})
        robot = get_robot(client, ROBOT)
        assert robot["status"] == "online" and robot["name"] == "Renamed"


# --- Streaming and viewing ------------------------------------------------------


def test_stream_returns_detections_in_dashboard_and_pi_formats(client):
    with client.websocket_connect(f"/ws/stream/{ROBOT}?model=fake", headers=KEY_HEADERS) as stream:
        stream.send_bytes(make_jpeg(320, 240))
        result = stream.receive_json()

    assert result["boxes"] == [FAKE_BOX]
    assert result["labels"] == ["whitefly"]
    assert result["image_size"] == [320, 240]
    # The Pi reads this list; without it every server detection arrived empty.
    assert result["detections"] == [{"class": "whitefly", "confidence": 0.9, "bbox": FAKE_BOX}]


def test_model_can_be_chosen_with_a_handshake_message(client, fake_adapter):
    with client.websocket_connect(f"/ws/stream/{ROBOT}", headers=KEY_HEADERS) as stream:
        stream.send_text('{"model": "fake"}')
        stream.send_bytes(make_jpeg())
        assert stream.receive_json()["labels"] == ["whitefly"]
    assert fake_adapter.infer_calls == 1


def test_unknown_model_falls_back_to_default_and_warns_once(client, caplog):
    with client.websocket_connect(f"/ws/stream/{ROBOT}?model=onnx", headers=KEY_HEADERS) as stream:
        for _ in range(3):
            stream.send_bytes(make_jpeg())
            assert stream.receive_json()["labels"] == ["whitefly"]
    warnings = [r for r in caplog.records if "unknown model" in r.getMessage()]
    assert len(warnings) == 1


def test_streaming_flag_follows_the_stream_socket(client):
    with client.websocket_connect(f"/ws/stream/{ROBOT}?model=fake", headers=KEY_HEADERS):
        assert wait_until(lambda: (get_robot(client, ROBOT) or {}).get("streaming") is True)
    assert wait_until(lambda: get_robot(client, ROBOT)["streaming"] is False)


def test_closing_the_stream_does_not_mark_robot_offline(client):
    with client.websocket_connect(f"/ws/control/{ROBOT}", headers=KEY_HEADERS) as control_ws:
        control_ws.send_json({"type": "heartbeat"})
        assert wait_until(lambda: get_robot(client, ROBOT)["status"] == "online")
        with client.websocket_connect(f"/ws/stream/{ROBOT}?model=fake", headers=KEY_HEADERS) as stream:
            stream.send_bytes(make_jpeg())
            stream.receive_json()
        assert not wait_until(lambda: get_robot(client, ROBOT)["status"] == "offline", timeout=0.5)


def test_viewer_receives_robot_frames_and_detections(client):
    frame = make_jpeg()
    with client.websocket_connect(f"/ws/view/{ROBOT}") as viewer:
        with client.websocket_connect(f"/ws/stream/{ROBOT}?model=fake", headers=KEY_HEADERS) as stream:
            stream.send_bytes(frame)
            stream.receive_json()

            received = {"frame": None, "detection": None}
            while None in received.values():
                message = viewer.receive()
                if message.get("bytes") is not None:
                    received["frame"] = message["bytes"]
                elif message.get("text") is not None:
                    received["detection"] = message["text"]

    assert received["frame"] == frame
    assert '"whitefly"' in received["detection"]


def test_several_viewers_watch_the_same_robot(client):
    frame = make_jpeg()
    with client.websocket_connect(f"/ws/view/{ROBOT}") as viewer_a, client.websocket_connect(f"/ws/view/{ROBOT}") as viewer_b:
        with client.websocket_connect(f"/ws/stream/{ROBOT}?model=fake", headers=KEY_HEADERS) as stream:
            stream.send_bytes(frame)
            stream.receive_json()
            for viewer in (viewer_a, viewer_b):
                frames = []
                while not frames:
                    message = viewer.receive()
                    if message.get("bytes") is not None:
                        frames.append(message["bytes"])
                assert frames == [frame]


def test_viewers_leaving_does_not_affect_the_robot(client):
    with client.websocket_connect(f"/ws/control/{ROBOT}", headers=KEY_HEADERS) as control_ws:
        control_ws.send_json({"type": "heartbeat"})
        assert wait_until(lambda: get_robot(client, ROBOT)["status"] == "online")
        with client.websocket_connect(f"/ws/stream/{ROBOT}?model=fake", headers=KEY_HEADERS) as stream:
            with client.websocket_connect(f"/ws/view/{ROBOT}"):
                pass
            # The robot still gets its detections after the viewer left.
            stream.send_bytes(make_jpeg())
            assert stream.receive_json()["labels"] == ["whitefly"]
        assert get_robot(client, ROBOT)["status"] == "online"


def test_stream_reconnect_keeps_detections_flowing_to_the_new_socket(client):
    with client.websocket_connect(f"/ws/stream/{ROBOT}?model=fake", headers=KEY_HEADERS) as old:
        with client.websocket_connect(f"/ws/stream/{ROBOT}?model=fake", headers=KEY_HEADERS) as new:
            with pytest.raises(WebSocketDisconnect):
                old.receive_json()
            new.send_bytes(make_jpeg())
            assert new.receive_json()["labels"] == ["whitefly"]


def test_ip_address_is_optional_when_adding_a_robot(client):
    response = client.post("/api/robots/register", json={"robot_id": ROBOT, "name": "Field 1"})
    assert response.status_code == 200
    assert response.json()["ip_address"] is None
