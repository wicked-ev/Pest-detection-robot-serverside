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
    │   └── RobotsContext.jsx    # Global robot state (Context + useRobotsContext hook)
    │
    ├── hooks/
    │   ├── useRobots.js        # Poll /api/robots every 5s
    │   ├── useRobotStream.js   # Stream WebSocket + detection rendering
    │   └── useControlSocket.js # Control WebSocket + heartbeat
    │
    ├── components/
    │   ├── layout/
    │   │   ├── TopBar.jsx          # Server health + title + timestamp
    │   │   └── Sidebar.jsx         # Robot list + Add button
    │   │
    │   ├── robots/
    │   │   ├── RobotCard.jsx       # Individual robot card with selection
    │   │   ├── RobotStatusBadge.jsx # Status indicator
    │   │   └── AddRobotModal.jsx   # Robot registration form
    │   │
    │   ├── stream/
    │   │   ├── StreamView.jsx      # Live feed + start/stop controls
    │   │   └── DetectionOverlay.jsx # Canvas with bounding boxes
    │   │
    │   ├── controls/
    │   │   ├── CommandPanel.jsx    # Command buttons + WiFi provisioning
    │   │   └── WifiModal.jsx       # SSID + password form
    │   │
    │   └── charts/
    │       └── DetectionChart.jsx  # Recharts area chart (last 60)
    │
    └── pages/
        ├── Dashboard.jsx      # Main layout (router-like structure)
        └── RobotDetail.jsx    # Split view: stream + info/controls
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

**The dev server automatically proxies:**
- `/api/*` → `http://localhost:8000/api/*`
- `/ws/*` → `ws://localhost:8000/ws/*`

### 3. Ensure FastAPI Server is Running

On another terminal:

```bash
cd server
pip install -r requirements.txt
# Place your ONNX/TFLite models in server/models/
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## Key Features Implemented

### 1. **Real-time Video Streaming**
   - StreamView component connects to `/ws/stream/{robot_id}`
   - Receives binary JPEG frames
   - Renders on `<img>` tag with live FPS counter
   - Detection JSON triggers overlay rendering

### 2. **WebSocket Management**
   - `RobotWebSocket` class with auto-reconnect + exponential backoff
   - Separate control socket (heartbeat + commands) per robot
   - Separate stream socket (frames + detections) per robot
   - Automatic cleanup on unmount

### 3. **Multi-model Support**
   - Stream endpoint accepts `?model=` query param
   - Falls back to first discovered model if not found
   - Model list exposed in REST API (`GET /api/models`)

### 4. **Robot Command Panel**
   - Start/Stop Stream
   - Reboot
   - Stop
   - WiFi Provisioning (provisioning mode only)

### 5. **Detection Analytics**
   - Real-time confidence score chart (last 60 points)
   - Latest detection labels
   - Bounding box overlay with label + confidence %

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
POST /api/robots/{robot_id}/wifi { ssid, password }
```

### WebSocket Endpoints

```javascript
// Control: Commands + Heartbeat
WS /ws/control/{robot_id}
  → Server sends: { "command": "..." }
  → Pi sends: { "type": "heartbeat", "status": "ok" }

// Stream: JPEG + Detections
WS /ws/stream/{robot_id}?model={model_name}
  → Pi sends: [binary JPEG frames]
  → Server sends: { "boxes": [...], "scores": [...], "labels": [...] }
```

## Configuration

### Environment Variables

Create `.env.local`:

```
REACT_APP_API_URL=http://your-api-server:8000
```

Default: `http://localhost:8000`

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
- [ ] `RobotCard.jsx` — Add click handler for robot settings/details panel
- [ ] `Dashboard.jsx` — Implement sidebar collapse for mobile

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
