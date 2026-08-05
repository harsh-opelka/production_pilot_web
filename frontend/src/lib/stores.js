import { writable } from 'svelte/store';

function persisted(key, initial) {
  let value = initial;
  try {
    const saved = localStorage.getItem(key);
    if (saved) value = JSON.parse(saved);
  } catch {
    // localStorage unavailable or corrupt — fall back to default
  }
  const store = writable(value);
  store.subscribe((v) => {
    try {
      localStorage.setItem(key, JSON.stringify(v));
    } catch {
      // ignore — not worth breaking the UI over a storage quota issue
    }
  });
  return store;
}

export const theme = persisted('pp_theme', 'dark');
export const lang = persisted('pp_lang', 'en');
export const view = persisted('pp_view', 'block');
export const page = writable('dashboard');

// { connected, timestamp, groups } — same shape as GET /api/machines
export const machinesState = writable({ connected: false, timestamp: null, groups: [] });

// True only while the WebSocket itself is open. The connection banner
// also considers machinesState.connected — either one being false means
// stale/no data, which is the dangerous case on a production-hall TV.
export const wsConnected = writable(false);

// Service-tab session token. Deliberately a plain (non-persisted) store,
// not run through persisted() — it must NOT survive a closed tab, since
// this gates config changes and password resets on a shared-network app.
export const serviceToken = writable(null);

// Set when a 401 clears an existing (not merely absent) token — lets the
// login prompt distinguish "your session expired" from "enter password".
export const serviceSessionExpired = writable(false);
