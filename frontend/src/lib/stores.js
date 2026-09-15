import { writable, readable } from 'svelte/store';

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

// 'dashboard' | 'statistics' | 'service' | 'settings' — which main-content
// view is showing. 'service' and 'settings' are only ever reachable while
// auth.level is 'service' (see Sidebar.svelte, which is the only thing
// that sets it).
export const page = writable('dashboard');

// { connected, timestamp, groups } — same shape as GET /api/machines
export const machinesState = writable({ connected: false, timestamp: null, groups: [] });

// True only while the WebSocket itself is open. The connection banner
// also considers machinesState.connected — either one being false means
// stale/no data, which is the dangerous case on a production-hall TV.
export const wsConnected = writable(false);

// Ticks once a second — shared by every live-elapsed-timer consumer
// (FryerTile, MachineListRow, Statistics' Live mode) so there's exactly
// ONE interval running for the whole app instead of one per tile/row.
// Timers derive elapsed time from (this - a server timestamp) rather
// than counting up locally, so they stay correct across reloads.
export const nowTick = readable(Date.now(), (set) => {
  const interval = setInterval(() => set(Date.now()), 1000);
  return () => clearInterval(interval);
});

// Gear-gate session: { token, level } where level is 'management' |
// 'service' | null. Deliberately a plain (non-persisted) store, not run
// through persisted() — it must NOT survive a closed tab (or a refresh:
// reloading is treated the same as logging out), since this gates
// config changes and password resets on a shared-network app.
export const auth = writable({ token: null, level: null });

// Pure UI state — whether the sidebar is CURRENTLY SHOWN, independent of
// whether the session is authenticated (see `auth` above). Deliberately
// a separate store rather than deriving "show sidebar" straight from
// `auth.token`: that used to make closing the sidebar indistinguishable
// from logging out, so reopening it (via the logo) re-prompted for the
// password even though the session was still valid. See serviceApi.js's
// login()/logout() (and its 401 handler) for where this gets set, and
// TopBar.svelte's logo click handler for the toggle-vs-prompt logic.
// App.svelte only renders <Sidebar> while BOTH this AND auth.token are
// true.
export const sidebarOpen = writable(false);
