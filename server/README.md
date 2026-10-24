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
- `GET /api/robots`, `GET /api/robots/{robot_id}`, `POST /api/robots/register` (`{robot_id, name, ip_address?}`)
- `DELETE /api/robots/{robot_id}`: removes a robot from the list (409 while it is connected); its history is kept.
- `POST /api/robots/{robot_id}/command` (`{command, ...}`): `start_stream`, `stop_stream`,
  `move` (`direction`, `speed` 10-100), `halt` (stop wheels and sprayer), `spray` (`duration` up to 5 s),
  `set_auto_spray` (`enabled`), `reboot`, `shutdown`. Returns 409 if the robot is not connected.
  Robots in the API include `live`: their last reported `state`, `motors`, `auto_spray`, `spraying`, `driving`.
- `GET /api/models`, `GET /api/models/{name}`, `GET /api/models/{name}/availability`

## Detection history

Detections are grouped into **sightings**: one pest type seen by one robot. Frames of the same
pest less than 30 seconds apart extend the current sighting (frame count, last seen, and the
photo of its most confident frame) instead of adding rows. Sightings are stored in the `sighting`
table of `robot_store.db`, with one photo each in `server/data/snapshots/<id>.jpg`.
Nothing is deleted automatically.

- `GET /api/sightings?robot_id=&label=&since=&before_id=&limit=`: newest first. For the next page,
  pass the last `id` you received as `before_id`. `since` is an ISO 8601 time.
- `GET /api/sightings/summary?robot_id=&since=`: number of sightings per pest type.
- `GET /api/sightings/{id}` and `GET /api/sightings/{id}/snapshot?v=` (the JPEG photo; `v` is the
  photo version in `snapshot_url`, so the photo always matches the boxes returned with it).
- `GET /api/sprays?robot_id=&limit=`: sprays reported by robots (newest first). Each sighting has
  `sprays`: how many sprays targeted that pest while it was in view.

Each sighting includes `boxes` (in photo pixels) and `image_width`/`image_height`, so the
dashboard draws the boxes over the photo.

Wi-Fi setup is not done through the server: an unprovisioned robot has no network.
The Pi starts its own hotspot for that (see the Pi project's `services/wifi_service.py`).

## Tests

```bash
uv sync                                # installs pytest (dev dependency) the first time
.venv/Scripts/python -m pytest         # fast suite, ~4 s, uses a fake model
.venv/Scripts/python -m pytest -m slow # only the slow test: loads the real models/pest_model.pt
```

- `tests/test_robot_connections.py`: robot key, self-registration, heartbeats and online/offline,
  commands, reconnects, streaming, and dashboard viewers.
- `tests/test_workers.py`: the inference worker (only the newest frame is processed) and viewer hub.
- `tests/test_model_adapters.py`: class-ID-to-pest-name mapping and RF-DETR checkpoint loading.
- `tests/test_model_loading.py`: the model loads once, and frames sent while it loads are not dropped.
- `tests/test_robot_store.py`: how often detections are written, timestamps, and startup cleanup.
- `tests/test_sightings.py`: grouping detections into sightings, photos, paging, and the history API.

Tests build the app with `create_app(model_registry=..., db_url=...)` in `main.py`, so they use a
temporary database and never touch `robot_store.db` or your `.env` key.

## Testing without the Pi

```bash
.venv/Scripts/python tools/send_test_image.py path/to/pest.jpg
```

Acts as a robot: sends one JPEG to `/ws/stream/test-robot` (with the key from `.env`) and prints the detections.
