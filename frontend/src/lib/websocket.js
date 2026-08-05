import { machinesState, wsConnected } from './stores.js';

const RECONNECT_DELAY_MS = 2000;

function wsUrl() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${location.host}/ws`;
}

function applyState(data) {
  machinesState.set({
    connected: data.connected,
    timestamp: data.timestamp,
    groups: data.groups,
  });
}

export async function fetchInitialState() {
  try {
    const res = await fetch('/api/machines');
    if (res.ok) applyState(await res.json());
  } catch {
    // WebSocket connect (below) will retry and eventually populate
    // state; the connection banner covers the user-visible gap.
  }
}

export function connectWebSocket() {
  const socket = new WebSocket(wsUrl());

  socket.addEventListener('open', () => {
    wsConnected.set(true);
  });

  socket.addEventListener('message', (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type === 'state') applyState(msg);
    // "heartbeat" messages need no handling — just receiving one (or
    // any message) proves the connection is alive.
  });

  const scheduleReconnect = () => {
    wsConnected.set(false);
    setTimeout(connectWebSocket, RECONNECT_DELAY_MS);
  };

  socket.addEventListener('close', scheduleReconnect);
  socket.addEventListener('error', () => socket.close());
}
