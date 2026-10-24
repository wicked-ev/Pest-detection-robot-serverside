# Pest Detection Robot Dashboard

Dark-themed React dashboard for watching and controlling pest detection robots.

## Features

- **Live** — each robot's camera feed with detection boxes, stream start/stop,
  Stop motors / Reboot / Shutdown, and its latest pest sightings
- **History** — every pest sighting with a photo, filterable by robot, pest and time range,
  with per-pest counts; click a sighting for the full photo and details
- **Robot list** — online robots first, with status, streaming state and last heartbeat;
  robots with the robot key appear by themselves, and offline robots can be removed

## Setup

Prerequisites: Node.js 18+ and the FastAPI server (see `../server/README.md`).

```bash
cd dashboard
npm install
npm run dev        # http://localhost:5173
```

The Vite dev server forwards `/api`, `/health` and `/ws` to the FastAPI server, so the
browser only ever talks to one address. If the server is not on this machine, copy
`.env.example` to `.env.local` and set its address:

```
VITE_SERVER_URL=http://192.168.1.8:8000
```

Use `127.0.0.1` rather than `localhost` for a local server: Node may resolve `localhost` to
IPv6 `::1`, which uvicorn does not listen on.

```bash
npm run build      # production build in dist/
npm run preview    # serve that build locally
```

## How it fits together

- `src/api/client.js` — REST calls (robots, commands, sightings)
- `src/api/websocket.js` — WebSocket wrapper with automatic reconnect
- `src/context/RobotsContext.jsx` — shared state: robots, selected robot, current page
- `src/hooks/useRobots.js` — polls `/api/robots` every 5 seconds
- `src/hooks/useRobotStream.js` — watches one robot through `/ws/view/{robot_id}`
  (receives frames and detections; never sends anything to the robot)
- `src/hooks/useSightings.js` — loads history pages and refreshes them
- `src/components/common/BoxOverlay.jsx` — draws boxes as an SVG in the image's own pixel
  coordinates, so they line up at any display size (used for the live feed and photos)
- `src/pages/RobotDetail.jsx` and `src/pages/History.jsx` — the two pages

## Design

Background `#0a0a0a`, surfaces `#111111` with `#222` borders, accent green `#22c55e`,
warning `#eab308`, danger `#ef4444`, text `#fafafa` / `#71717a`, 8 px cards, 6 px buttons.
Font: Inter (loaded from Google Fonts; without internet the browser's default sans-serif is used).

## Known issues

- `vite` 8 is installed, but `@vitejs/plugin-react` 4 officially supports Vite up to 7. It works,
  but `npm install` / `npm uninstall` refuse changes unless you add `--legacy-peer-deps`.
  Upgrading the plugin would fix this.
