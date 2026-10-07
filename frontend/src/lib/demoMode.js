import { writable } from 'svelte/store';

// Customer Demo Mode — which screen is shown (live Pilot or the looping
// demo video), the demo's server status, and the small pure rules the
// Demo button / overlay use. Recording itself: demoRecorder.js.

// --- Live / Demo mode, remembered across reloads (trade-fair kiosk) -------

export const MODE_STORAGE_KEY = 'pp_display_mode';

function defaultStorage() {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null; // e.g. storage blocked: accessing it throws
  }
}

/** 'demo' or 'live' (the fallback whenever storage is missing, blocked or holds anything else). */
export function loadMode(storage = defaultStorage()) {
  try {
    return storage?.getItem(MODE_STORAGE_KEY) === 'demo' ? 'demo' : 'live';
  } catch {
    return 'live';
  }
}

export function saveMode(mode, storage = defaultStorage()) {
  try {
    storage?.setItem(MODE_STORAGE_KEY, mode === 'demo' ? 'demo' : 'live');
  } catch {
    // Not worth breaking the screen over — it just won't be remembered.
  }
}

export const displayMode = writable(loadMode());
displayMode.subscribe((mode) => saveMode(mode));

// --- Server status (GET /api/demo/status) --------------------------------

export const demoStatus = writable({ exists: false, duration_seconds: null, size_bytes: null, recorded_at: null, show_for_all: false, loaded: false });

/** Refreshes demoStatus; true if the server answered, false if it could not be reached. */
export async function loadDemoStatus() {
  try {
    const res = await fetch('/api/demo/status');
    if (!res.ok) return false;
    demoStatus.set({ ...(await res.json()), loaded: true });
    return true;
  } catch {
    return false; // server not reachable
  }
}

// Short user-facing message under the Demo button: { key, vars } or null.
export const demoMessage = writable(null);
let messageTimer;
export function showDemoMessage(key, vars = {}, ms = 8000) {
  clearTimeout(messageTimer);
  demoMessage.set({ key, vars });
  if (ms) messageTimer = setTimeout(() => demoMessage.set(null), ms);
}

// --- Rules ------------------------------------------------------------------

/** Is the Demo (play) button shown? Service always; others only if the Service setting allows it. */
export function demoButtonVisible(level, showForAll) {
  return level === 'service' || !!showForAll;
}

/** Record / Stop / Delete are Service-only. */
export function canManageDemo(level) {
  return level === 'service';
}

/**
 * Can this browser record the tab? Needs a secure context (https or
 * localhost — getDisplayMedia doesn't exist otherwise) and tab capture +
 * MediaRecorder support. Returns { ok, reasonKey } (translation key).
 */
export function recordSupport(win = globalThis) {
  if (!win?.isSecureContext) return { ok: false, reasonKey: 'demo_record_insecure' };
  if (!win.navigator?.mediaDevices?.getDisplayMedia || typeof win.MediaRecorder !== 'function') {
    return { ok: false, reasonKey: 'demo_record_unsupported' };
  }
  return { ok: true, reasonKey: null };
}

/** Which hover-menu entries are enabled. `phase`: demoRecorder phase
 *  ('idle' | 'prompt' | 'recording' | 'saving' | 'failed' — failed = the
 *  last recording couldn't be saved; a new recording may replace it). */
export function menuEntries(phase, support) {
  const canStart = phase === 'idle' || phase === 'failed';
  return {
    record: { enabled: canStart && support.ok, reasonKey: canStart ? support.reasonKey : null },
    stop: { enabled: phase === 'recording' },
  };
}

/** The real reason a save failed, as { key, vars } for translate(): the
 *  HTTP status + server message, or which network error it was. */
export function describeUploadError(err) {
  if (err?.name === 'NetworkError') {
    return { key: err.kind === 'timeout' ? 'demo_upload_timeout' : 'demo_upload_network', vars: {} };
  }
  if (err?.status === 401) return { key: 'demo_upload_auth', vars: { detail: err.message } };
  if (typeof err?.status === 'number') return { key: 'demo_upload_http', vars: { detail: err.message } };
  return { key: 'demo_upload_other', vars: { detail: `${err?.name ?? 'Error'}: ${err?.message ?? String(err)}` } };
}

/** Automatic retry only makes sense when no response arrived at all. */
export function isRetryableUploadError(err) {
  return err?.name === 'NetworkError';
}

/** Player fallback: after `which` failed, the source to try next (or null = give up, show Live). */
export function nextPlaybackSource(which, status) {
  return which === 'current' && status?.has_previous ? 'previous' : null;
}

/** "mm:ss" for the REC timer and the player. */
export function formatClock(seconds) {
  const s = Math.max(0, Math.floor(Number.isFinite(seconds) ? seconds : 0));
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
}

/** Video URL: versioned so a new recording is never served from cache;
 *  the token (if any) because a <video> can't send an Authorization header. */
export function demoVideoUrl(status, token, which = 'current') {
  const params = new URLSearchParams({ v: status?.version ?? status?.recorded_at ?? '' });
  if (which === 'previous') params.set('which', 'previous');
  if (token) params.set('token', token);
  return `/api/demo/video?${params}`;
}
