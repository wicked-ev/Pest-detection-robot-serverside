"""Drive and spray commands, the robot's live status, and spray history."""

import json

import pytest

from conftest import KEY_HEADERS, get_robot, make_jpeg, wait_until

ROBOT = "robot-1"
CONTROL = f"/ws/control/{ROBOT}"


def command(client, **body):
    return client.post(f"/api/robots/{ROBOT}/command", json=body)


# --- Commands ------------------------------------------------------------------------------


def test_move_is_sent_with_direction_and_speed(client):
    with client.websocket_connect(CONTROL, headers=KEY_HEADERS) as robot:
        assert wait_until(lambda: get_robot(client, ROBOT) is not None)
        assert command(client, command="move", direction="left", speed=60).status_code == 200
        assert robot.receive_json() == {"command": "move", "direction": "left", "speed": 60}


@pytest.mark.parametrize(
    "body",
    [
        {"command": "move"},                                  # no direction
        {"command": "move", "direction": "up"},               # unknown direction
        {"command": "move", "direction": "left", "speed": 500},
        {"command": "spray", "duration": 30},                 # longer than 5 s
        {"command": "set_auto_spray"},                        # no on/off
    ],
    ids=["no-direction", "bad-direction", "bad-speed", "too-long", "no-enabled"],
)
def test_invalid_drive_and_spray_commands_are_rejected(client, body):
    with client.websocket_connect(CONTROL, headers=KEY_HEADERS):
        assert wait_until(lambda: get_robot(client, ROBOT) is not None)
        assert command(client, **body).status_code in (400, 422)


def test_spray_and_auto_spray_commands_reach_the_robot(client):
    with client.websocket_connect(CONTROL, headers=KEY_HEADERS) as robot:
        assert wait_until(lambda: get_robot(client, ROBOT) is not None)
        command(client, command="spray", duration=1.5)
        assert robot.receive_json() == {"command": "spray", "duration": 1.5}
        command(client, command="set_auto_spray", enabled=True)
        assert robot.receive_json() == {"command": "set_auto_spray", "enabled": True}


# --- Live status ----------------------------------------------------------------------------


def test_live_status_comes_from_heartbeats_and_updates(client):
    with client.websocket_connect(CONTROL, headers=KEY_HEADERS) as robot:
        robot.send_json({"type": "heartbeat", "state": "READY", "motors": True, "auto_spray": False,
                         "spraying": False, "driving": None, "secret": "ignored"})
        assert wait_until(lambda: (get_robot(client, ROBOT) or {}).get("live"))
        live = get_robot(client, ROBOT)["live"]
        assert live == {"state": "READY", "motors": True, "auto_spray": False, "spraying": False, "driving": None}

        robot.send_json({"type": "live", "auto_spray": True, "spraying": True})
        assert wait_until(lambda: get_robot(client, ROBOT)["live"]["auto_spray"] is True)
        assert get_robot(client, ROBOT)["live"]["spraying"] is True

    assert wait_until(lambda: get_robot(client, ROBOT)["live"] is None)  # gone once disconnected


# --- Spray reports and history -----------------------------------------------------------------


def report_spray(robot, **fields):
    robot.send_json({"type": "spray", "trigger": "auto", "label": "whitefly", "confidence": 0.9,
                     "duration": 1.0, **fields})


def test_spray_reports_are_stored_and_shown_to_viewers(client):
    with client.websocket_connect(f"/ws/view/{ROBOT}") as viewer:
        with client.websocket_connect(CONTROL, headers=KEY_HEADERS) as robot:
            report_spray(robot)
            event = json.loads(viewer.receive_text())
    assert event["type"] == "spray" and event["label"] == "whitefly" and event["trigger"] == "auto"
    [spray] = client.get("/api/sprays").json()
    assert spray["robot_id"] == ROBOT and spray["duration"] == 1.0


def test_sightings_show_how_often_they_were_sprayed(client):
    # The fake model detects a "whitefly" in every frame, creating a sighting.
    with client.websocket_connect(f"/ws/stream/{ROBOT}?model=fake", headers=KEY_HEADERS) as stream:
        stream.send_bytes(make_jpeg())
        stream.receive_json()
    assert wait_until(lambda: client.get("/api/sightings").json() != [])

    with client.websocket_connect(CONTROL, headers=KEY_HEADERS) as robot:
        report_spray(robot)
        report_spray(robot, label="mealy bug")   # a different pest: not this sighting
        report_spray(robot, label=None, trigger="manual")  # manual, no target
        assert wait_until(lambda: len(client.get("/api/sprays").json()) == 3)

    [sighting] = client.get("/api/sightings").json()
    assert sighting["sprays"] == 1
    assert client.get(f"/api/sightings/{sighting['id']}").json()["sprays"] == 1


def test_malformed_spray_reports_are_ignored(client):
    with client.websocket_connect(CONTROL, headers=KEY_HEADERS) as robot:
        report_spray(robot, duration="long")
        report_spray(robot)
        assert wait_until(lambda: len(client.get("/api/sprays").json()) == 1)
