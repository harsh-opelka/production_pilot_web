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

// Manual display-scale (0.7-3.0), independent per device/browser so a
// phone and a wall-mounted TV can each keep their own preferred size.
export const uiScale = persisted('pp_ui_scale', 1);

// 'dashboard' | 'statistics' | 'service' — which main-content view is
// showing. 'service' is only ever reachable while auth.level is
// 'service' (see Sidebar.svelte, which is the only thing that sets it).
export const page = writable('dashboard');

// { connected, timestamp, groups } — same shape as GET /api/machines
export const machinesState = writable({ connected: false, timestamp: null, groups: [] });

// True only while the WebSocket itself is open. The connection banner
// also considers machinesState.connected — either one being false means
// stale/no data, which is the dangerous case on a production-hall TV.
export const wsConnected = writable(false);

// Gear-gate session: { token, level } where level is 'management' |
// 'service' | null. Deliberately a plain (non-persisted) store, not run
// through persisted() — it must NOT survive a closed tab (or a refresh:
// reloading is treated the same as logging out), since this gates
// config changes and password resets on a shared-network app.
export const auth = writable({ token: null, level: null });
