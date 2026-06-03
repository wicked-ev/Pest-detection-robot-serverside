# Pest Detection Robot Dashboard

Dark-themed React dashboard for monitoring and controlling pest detection robots in real-time.

## Features

- **Real-time Video Streaming** — Live feed with detection overlays
- **WebSocket-powered** — Binary frame reception + JSON detection results
- **Multi-model Support** — Switch between ONNX, TFLite, and RF-DTR models per robot
- **Detection Analytics** — Real-time confidence score charting
- **Command Panel** — Start/stop streams, reboot, send WiFi credentials
- **Robot Registry** — Add, list, and monitor robot status
- **Dark Theme** — Minimal Vercel/Linear-inspired UI

## Setup

### Prerequisites

- Node.js 18+
- The FastAPI server running on `http://localhost:8000` (configurable via environment variables)

### Installation

```bash
cd dashboard
npm install
```

### Development

```bash
npm run dev
```

The app will be available at `http://localhost:5173` with proxy forwarding to the API server.

### Build

```bash
npm run build
npm run preview  # Local preview of production build
```

## Architecture

### API Integration

- REST client with automatic retry and error handling (`src/api/client.js`)
- WebSocket manager with exponential backoff reconnection (`src/api/websocket.js`)
- Context-based global state management (`src/context/RobotsContext.jsx`)

### Hooks

- `useRobots()` — Polls `/api/robots` every 5 seconds
- `useRobotStream()` — Manages stream WebSocket + detection rendering
- `useControlSocket()` — Maintains control socket + heartbeat

### Components

**Layout**
- `TopBar` — Server health indicator, title, timestamp
- `Sidebar` — Robot list with status badges, "Add Robot" button

**Robots**
- `RobotCard` — Individual robot overview with selection
- `RobotStatusBadge` — Status indicator (online/provisioning/offline)
- `AddRobotModal` — Registration form for new robots

**Stream**
- `StreamView` — Live video feed with start/stop controls
- `DetectionOverlay` — Bounding boxes + labels drawn on canvas

**Controls**
- `CommandPanel` — Stream/reboot/stop buttons
- `WifiModal` — WiFi credentials provisioning form

**Charts**
- `DetectionChart` — Recharts area chart of last 60 detections

## Design System

- **Background**: `#0a0a0a`
- **Surface**: `#111111` with `1px solid #222` border
- **Accent**: `#22c55e` (green)
- **Warning**: `#eab308` (yellow)
- **Danger**: `#ef4444` (red)
- **Text**: `#fafafa` primary, `#71717a` secondary
- **Radius**: `8px` cards, `6px` buttons
- **Font**: Inter

## Environment Variables

Create a `.env.local` file if using a non-local API:

```
REACT_APP_API_URL=http://your-api-host:8000
```

The Vite dev server proxy is configured in `vite.config.js`.

## Browser Support

Modern browsers with WebSocket and ES6 support (Chrome, Firefox, Safari, Edge).

## TODO

- [ ] Add authentication token header to fetch calls (when auth is implemented)
- [ ] Model selection UI in the stream settings
- [ ] Robot provisioning discovery via mDNS
- [ ] Export detection logs as CSV
- [ ] Mobile-responsive design enhancements
