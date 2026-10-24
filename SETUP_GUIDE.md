# 🚀 Pest Detection Robot Dashboard — Setup Guide

## Project Structure Created

```
dashboard/
├── .env.example                 # Environment variables template
├── .gitignore                  
├── index.html                   # HTML entry point
├── package.json                 # Dependencies & scripts
├── postcss.config.js           # PostCSS configuration
├── tailwind.config.js          # TailwindCSS configuration
├── vite.config.js              # Vite configuration with API proxy
├── README.md                   # Full documentation
│
└── src/
    ├── main.jsx                # React entry
    ├── App.jsx                 # Root component
    ├── index.css               # Global styles
    │
    ├── api/
    │   ├── client.js           # REST client with APIClient class
    │   └── websocket.js        # RobotWebSocket manager class
    │
    ├── context/
    │   └── RobotsContext.jsx    # Robots, selected robot, current page (Live/History)
    │
    ├── hooks/
    │   ├── useRobots.js        # Poll /api/robots every 5s
    │   ├── useRobotStream.js   # Viewer WebSocket: live frames + detections
    │   └── useSightings.js     # Detection history with paging and auto-refresh
    │
    ├── utils/
    │   └── time.js             # "2 min ago", dates, durations
    │
    ├── components/
    │   ├── common/
    │   │   ├── BoxOverlay.jsx      # SVG detection boxes over any image
    │   │   └── Panel.jsx           # Bordered section box
    │   │
    │   ├── layout/
    │   │   ├── TopBar.jsx          # Title, Live/History tabs, server status
    │   │   └── Sidebar.jsx         # Robot list + Add
    │   │
    │   ├── robots/
    │   │   ├── RobotCard.jsx       # One robot in the list
    │   │   ├── RobotStatusBadge.jsx # Online/offline badge
    │   │   └── AddRobotModal.jsx   # Name a robot in advance
    │   │
    │   ├── stream/
    │   │   └── StreamView.jsx      # Live feed with boxes + start/stop
    │   │
    │   ├── controls/
    │   │   └── CommandPanel.jsx    # Stop motors / Reboot / Shutdown
    │   │
    │   └── history/
    │       ├── SightingPhoto.jsx   # Sighting photo with its boxes
    │       ├── SightingCard.jsx    # One sighting in a grid
    │       ├── SightingModal.jsx   # Full photo and details
    │       └── RecentSightings.jsx # Latest sightings on the robot page
    │
    └── pages/
        ├── RobotDetail.jsx    # Live page: stream, controls, recent sightings
        └── History.jsx        # History page: filters, per-pest counts, sightings
```

## Quick Start

### 1. Install Dependencies

```bash
cd dashboard
npm install
```

### 2. Start Development Server

```bash
npm run dev
```

The dashboard will be available at `http://localhost:5173`.

**The dev server automatically proxies** `/api/*`, `/health` and `/ws/*` to the FastAPI server
(`http://127.0.0.1:8000` unless `VITE_SERVER_URL` is set in `dashboard/.env.local`).

### 3. Ensure FastAPI Server is Running

On another terminal:

```bash
cd server
uv sync                      # or: pip install -r requirements.txt
cp .env.example .env         # set ROBOT_KEY, the same value as on the Pi
# Place pest_model.pt and _annotations.coco.json in server/models/ (see server/models/README.md)
.venv/Scripts/python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

## Key Features Implemented

### 1. **Real-time Video Streaming**
   - The robot detail page opens one viewer socket, `/ws/view/{robot_id}`
   - The dashboard only watches: it never uses the robot's own `/ws/stream` or `/ws/control` sockets
   - Receives binary JPEG frames
   - Renders on `<img>` tag with live FPS counter
   - Detection JSON triggers overlay rendering

### 2. **WebSocket Management**
   - `RobotWebSocket` class with auto-reconnect + exponential backoff
   - Separate control socket (heartbeat + commands) per robot
   - Separate stream socket (frames + detections) per robot
   - Automatic cleanup on unmount

### 3. **Multi-model Support**
   - The robot picks the model with `?model=` on its stream socket (unknown names use the default, with one warning)
   - Falls back to first discovered model if not found
   - Model list exposed in REST API (`GET /api/models`)

### 4. **Robot Command Panel**
   - Start/Stop Stream (on the stream view)
   - Stop Motors (`halt`; the robot stays on)
   - Reboot and Shutdown (both ask for confirmation)
   - Wi-Fi is set up on the robot's own hotspot, not from the dashboard

### 5. **Detection History**
   - History tab: every pest sighting with its photo, filterable by robot, pest and time range
   - Per-pest counts; click a sighting for the full photo and details
   - The robot page shows its latest sightings next to the live stream

### 6. **Live Detection Overlay**
   - Boxes with pest name + confidence % drawn over the live stream

### 6. **Dark Theme**
   - Minimal, clean aesthetic (Vercel/Linear inspired)
   - No gradients, no box-shadows — borders only
   - Accent green (`#22c55e`), warning yellow, danger red
   - TailwindCSS with custom color palette

## API Integration

### REST Endpoints Called

```javascript
// Health & Discovery
GET /health
GET /api/robots
GET /api/robots/{robot_id}
GET /api/models
GET /api/models/{model_name}

// Commands
POST /api/robots/register { robot_id, name, ip_address }
POST /api/robots/{robot_id}/command { command }
```

### WebSocket Endpoints

```javascript
// Robot only (header X-Robot-Key must match the server's ROBOT_KEY)
WS /ws/control/{robot_id}
  → Server sends: { "command": "..." }
  → Pi sends: { "type": "heartbeat", "state": "..." }
WS /ws/stream/{robot_id}?model={model_name}
  → Pi sends: [binary JPEG frames]
  → Server sends: { "boxes", "scores", "labels", "detections", "image_size" }

// Dashboard only
WS /ws/view/{robot_id}
  → Server sends: [binary JPEG frames from the robot] and the same detection JSON
```

## Configuration

### Environment Variables

Copy `.env.example` to `.env.local` and set where the FastAPI server runs:

```
VITE_SERVER_URL=http://192.168.1.8:8000
```

Default: `http://127.0.0.1:8000` (not `localhost`: Node may resolve it to IPv6 `::1`, which uvicorn does not listen on). Vite only exposes variables prefixed with `VITE_`.

### TailwindCSS Custom Colors

Edit `tailwind.config.js` to customize:
- `background`: `#0a0a0a`
- `surface`: `#111111`
- `border`: `#222222`
- `accent`: `#22c55e`
- `warning`: `#eab308`
- `danger`: `#ef4444`

## Production Build

```bash
npm run build
npm run preview
```

Output: `dist/` directory ready for deployment.

## Browser Support

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+
- Requires WebSocket + ES6 support

## TODO Comments

- [ ] `client.js` — Add auth token headers to fetch calls when auth is implemented
- [ ] `RobotDetail.jsx` — Model selection UI for switching models mid-stream

## Troubleshooting

**WebSocket connection refused?**
- Check FastAPI server is running on `:8000`
- Verify proxy settings in `vite.config.js`

**Images not loading?**
- Ensure robot is sending valid JPEG frames
- Check network tab in DevTools for frame data

**Detection overlay not showing?**
- Verify robot is sending detection JSON on stream WebSocket
- Check console for parsing errors

## Performance Notes

- Frame URLs are revoked immediately after rendering (memory efficient)
- Detection overlay fades after 2 seconds if no new detection
- Charts keep only 60 points in memory (auto-prune older data)
- Context-based state avoids unnecessary re-renders
- WebSocket reconnect caps at 10s backoff max

---

**Ready to start!** Run `npm run dev` and navigate to the sidebar to add your first robot. 🤖
