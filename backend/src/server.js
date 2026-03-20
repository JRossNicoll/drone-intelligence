/**
 * Drone Intelligence Backend - Main Server
 *
 * Express REST API + WebSocket for real-time event streaming.
 */

const express = require('express');
const cors = require('cors');
const http = require('http');
const path = require('path');
const { WebSocketServer } = require('ws');

const { RulesEngine } = require('./rulesEngine');
const { EventStore } = require('./eventStore');
const { ConfigManager } = require('./configManager');
const { createApiRoutes } = require('./routes');

const PORT = process.env.BACKEND_PORT || 3000;
const VISION_WS_URL = process.env.VISION_WS_URL || 'ws://localhost:8000/ws';
const VISION_API_URL = process.env.VISION_API_URL || 'http://localhost:8000';

// Initialize components
const configManager = new ConfigManager(
  path.join(__dirname, '../../config/watchlist.json'),
  path.join(__dirname, '../../config/zones.json')
);
const eventStore = new EventStore(path.join(__dirname, '../../data/events'));
const rulesEngine = new RulesEngine(configManager, eventStore);

// Express app
const app = express();
app.use(cors());
app.use(express.json());

// Serve frontend static files
app.use(express.static(path.join(__dirname, '../../frontend')));

// API routes
const apiRoutes = createApiRoutes(configManager, eventStore, rulesEngine);
app.use('/api', apiRoutes);

// Vision service proxy info
app.get('/api/vision/config', (req, res) => {
  res.json({
    vision_api_url: VISION_API_URL,
    vision_ws_url: VISION_WS_URL,
  });
});

// HTTP server
const server = http.createServer(app);

// WebSocket server for frontend clients
const wss = new WebSocketServer({ server, path: '/ws' });
const frontendClients = new Set();

wss.on('connection', (ws) => {
  frontendClients.add(ws);
  console.log(`[WS] Frontend client connected. Total: ${frontendClients.size}`);

  ws.on('close', () => {
    frontendClients.delete(ws);
    console.log(`[WS] Frontend client disconnected. Total: ${frontendClients.size}`);
  });

  ws.on('message', (data) => {
    try {
      const msg = JSON.parse(data.toString());
      if (msg.type === 'ping') {
        ws.send(JSON.stringify({ type: 'pong' }));
      }
    } catch (e) {
      // Ignore invalid messages
    }
  });

  // Send recent events on connect
  const recentEvents = eventStore.getRecentEvents(20);
  ws.send(JSON.stringify({
    type: 'initial_events',
    events: recentEvents,
  }));
});

/**
 * Broadcast message to all connected frontend clients.
 */
function broadcastToFrontend(message) {
  const data = JSON.stringify(message);
  for (const client of frontendClients) {
    if (client.readyState === 1) { // WebSocket.OPEN
      try {
        client.send(data);
      } catch (e) {
        // Client will be cleaned up on close
      }
    }
  }
}

// Connect to vision service WebSocket
const WebSocket = require('ws');
let visionWs = null;
let visionReconnectTimer = null;

function connectToVision() {
  console.log(`[Vision] Connecting to ${VISION_WS_URL}...`);

  try {
    visionWs = new WebSocket(VISION_WS_URL);
  } catch (e) {
    console.log(`[Vision] Connection error: ${e.message}`);
    scheduleVisionReconnect();
    return;
  }

  visionWs.on('open', () => {
    console.log('[Vision] Connected to vision service');
  });

  visionWs.on('message', (data) => {
    try {
      const results = JSON.parse(data.toString());

      if (results.type === 'frame_results') {
        // Evaluate rules against tracked objects
        const events = rulesEngine.evaluate(results);

        // Broadcast detections + any new events to frontend
        broadcastToFrontend({
          type: 'frame_update',
          timestamp: results.timestamp,
          frame_number: results.frame_number,
          elapsed_ms: results.elapsed_ms,
          detections: results.detections,
          tracked_objects: results.tracked_objects,
          zone_events: results.zone_events || [],
          person_count: results.person_count,
          frame_shape: results.frame_shape,
          new_events: events,
        });
      }
    } catch (e) {
      console.error('[Vision] Parse error:', e.message);
    }
  });

  visionWs.on('close', () => {
    console.log('[Vision] Disconnected from vision service');
    scheduleVisionReconnect();
  });

  visionWs.on('error', (err) => {
    console.log(`[Vision] WebSocket error: ${err.message}`);
  });
}

function scheduleVisionReconnect() {
  if (visionReconnectTimer) return;
  visionReconnectTimer = setTimeout(() => {
    visionReconnectTimer = null;
    connectToVision();
  }, 3000);
}

// Start server
server.listen(PORT, () => {
  console.log(`[Server] Backend running on http://localhost:${PORT}`);
  console.log(`[Server] WebSocket on ws://localhost:${PORT}/ws`);
  console.log(`[Server] Vision API: ${VISION_API_URL}`);

  // Connect to vision service after short delay
  setTimeout(connectToVision, 2000);
});

// Graceful shutdown
process.on('SIGINT', () => {
  console.log('\n[Server] Shutting down...');
  if (visionWs) visionWs.close();
  server.close();
  process.exit(0);
});
