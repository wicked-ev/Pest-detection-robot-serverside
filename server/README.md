# Pest Detection Robot Server

FastAPI server that runs pest detection on camera frames sent by the robot (Raspberry Pi)
and relays the live feed and detections to the dashboard.

## Run

```bash
cd server
uv sync                      # or: python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
cp .env.example .env         # then set ROBOT_KEY (same value as on the Pi)
.venv/Scripts/python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Put the model files in `models/` first (see [models/README.md](models/README.md)).
Wait for `Preloaded default model pest_model` in the log before sending frames.

## Configuration (`server/.env`)

| Variable | Purpose |
|---|---|
| `ROBOT_KEY` | Shared secret robots must send in the `X-Robot-Key` header on their websockets. Empty disables the check (a warning is logged at startup). |

## Connections

| Endpoint | Who connects | Direction |
|---|---|---|
| `WS /ws/control/{robot_id}` | Robot only (needs key) | Robot → heartbeats every few seconds (marks it `online`); server → queued commands |
| `WS /ws/stream/{robot_id}?model=pest_model` | Robot only (needs key) | Robot → JPEG frames; server → detections |
| `WS /ws/view/{robot_id}` | Dashboard | Server → the robot's JPEG frames (binary) and detections (JSON) |

A robot is registered automatically the first time it connects with a valid key.
It is `offline` when its control socket closes or sends no heartbeat for 40 seconds.

Detection messages look like:

```json
{
  "boxes": [[x1, y1, x2, y2]], "scores": [0.91], "labels": ["whitefly"],
  "detections": [{"class": "whitefly", "confidence": 0.91, "bbox": [x1, y1, x2, y2]}],
  "image_size": [width, height]
}
```

`boxes`/`scores`/`labels` are used by the dashboard; `detections` matches the Pi's local model output.

## REST API

- `GET /health`
- `GET /api/robots`, `GET /api/robots/{robot_id}`, `POST /api/robots/register` (`{robot_id, name, ip_address}`)
- `POST /api/robots/{robot_id}/command` (`{command}`): one of `start_stream`, `stop_stream`, `halt` (stop motors),
  `reboot`, `shutdown`. Returns 409 if the robot is not connected.
- `GET /api/models`, `GET /api/models/{name}`, `GET /api/models/{name}/availability`

Wi-Fi setup is not done through the server: an unprovisioned robot has no network.
The Pi starts its own hotspot for that (see the Pi project's `services/wifi_service.py`).

## Testing without the Pi

```bash
.venv/Scripts/python tools/send_test_image.py path/to/pest.jpg
```

Acts as a robot: sends one JPEG to `/ws/stream/test-robot` (with the key from `.env`) and prints the detections.
