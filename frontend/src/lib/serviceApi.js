import { get } from 'svelte/store';
import { auth, sidebarOpen } from './stores.js';

export class ServiceApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

/**
 * Fetch wrapper for every protected call except login. Attaches the
 * current token, and on a 401 clears the auth store — the session is
 * gone (expired or the server restarted), so the UI must drop back to
 * the unauthenticated Production view rather than keep pretending it's
 * still authorized (see App.svelte's $effect on $auth.token). Also
 * closes the sidebar (see stores.js's sidebarOpen) — with no valid
 * session left, there's nothing for it to keep showing.
 */
async function serviceFetch(path, options = {}) {
  const { token } = get(auth);
  const headers = { ...(options.headers || {}) };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  if (options.body && !headers['Content-Type']) headers['Content-Type'] = 'application/json';

  const res = await fetch(path, { ...options, headers });

  let data = null;
  try {
    data = await res.json();
  } catch {
    // No/invalid JSON body — data stays null, message falls back below.
  }

  if (res.status === 401) {
    auth.set({ token: null, level: null });
    sidebarOpen.set(false);
    throw new ServiceApiError(data?.detail ?? 'Not authenticated', 401);
  }

  if (!res.ok) {
    throw new ServiceApiError(data?.detail ?? `Request failed (${res.status})`, res.status);
  }

  return data;
}

/**
 * Not routed through serviceFetch: there's no token yet to attach, and a
 * 401 here means "wrong password", not "your session expired" — the
 * caller (AuthGate) handles that distinction itself.
 */
export async function login(password) {
  const res = await fetch('/api/service/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  });

  let data = null;
  try {
    data = await res.json();
  } catch {
    // handled by !res.ok below
  }

  if (!res.ok) {
    throw new ServiceApiError(data?.detail ?? `Request failed (${res.status})`, res.status);
  }

  auth.set({ token: data.token, level: data.level });
  // Opens the sidebar on a fresh login — see TopBar.svelte's logo click
  // handler, which never calls login() again while already authenticated,
  // so this only ever fires once per session (not on every reopen).
  sidebarOpen.set(true);
}

export function logout() {
  auth.set({ token: null, level: null });
  sidebarOpen.set(false);
}

export function scanNetwork(subnet, port) {
  return serviceFetch('/api/service/scan', {
    method: 'POST',
    body: JSON.stringify({ subnet, port }),
  });
}

export function getServiceConfig() {
  return serviceFetch('/api/service/config');
}

export function saveServiceConfig(machines) {
  return serviceFetch('/api/service/config', {
    method: 'POST',
    body: JSON.stringify({ machines }),
  });
}

export function changePassword(currentPassword, newPassword) {
  return serviceFetch('/api/service/password', {
    method: 'POST',
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
}

export function changeManagementPassword(newPassword, confirmPassword) {
  return serviceFetch('/api/service/password/management', {
    method: 'POST',
    body: JSON.stringify({ new_password: newPassword, confirm_password: confirmPassword }),
  });
}

export function getRecordingStatus() {
  return serviceFetch('/api/service/recording-status');
}

export function setRecording(enabled) {
  return serviceFetch('/api/service/recording', {
    method: 'POST',
    body: JSON.stringify({ enabled }),
  });
}

export function clearHistory() {
  return serviceFetch('/api/service/history/clear', {
    method: 'POST',
    body: JSON.stringify({ confirm: true }),
  });
}

export function getHistorySummary() {
  return serviceFetch('/api/service/history/summary');
}

export function getDataSource() {
  return serviceFetch('/api/service/data-source');
}

export function setDataSource(mode) {
  return serviceFetch('/api/service/data-source', {
    method: 'POST',
    body: JSON.stringify({ mode }),
  });
}

export function getDemoState() {
  return serviceFetch('/api/service/demo/state');
}

export function setDemoPlcState(groupName, ip, changes) {
  return serviceFetch('/api/service/demo/set-state', {
    method: 'POST',
    body: JSON.stringify({ group_name: groupName, ip, ...changes }),
  });
}

export function getAvailableDates() {
  return serviceFetch('/api/stats/available-dates');
}

export function getDailySummary(date, compare) {
  const params = new URLSearchParams({ date });
  if (compare) params.set('compare', compare);
  return serviceFetch(`/api/stats/daily-summary?${params.toString()}`);
}

export function getRangeSummary(start, end) {
  return serviceFetch(`/api/stats/range-summary?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`);
}

export function getTimeline(date) {
  return serviceFetch(`/api/stats/timeline?date=${encodeURIComponent(date)}`);
}

export function getProductivityTarget() {
  return serviceFetch('/api/service/productivity-target');
}

// New Cycle start delay — GET is open (like the Hot/Cold threshold), PUT Service-only.
export function getNewCycleDelay() {
  return serviceFetch('/api/service/new-cycle-delay');
}

export function setNewCycleDelay(delaySeconds) {
  return serviceFetch('/api/service/new-cycle-delay', {
    method: 'PUT',
    body: JSON.stringify({ delay_seconds: delaySeconds }),
  });
}

export function getHotColdThreshold() {
  return serviceFetch('/api/service/hot-cold-threshold');
}

export function setHotColdThreshold(thresholdC) {
  return serviceFetch('/api/service/hot-cold-threshold', {
    method: 'PUT',
    body: JSON.stringify({ threshold_c: thresholdC }),
  });
}

export function setProductivityTarget(targetPct) {
  return serviceFetch('/api/service/productivity-target', {
    method: 'POST',
    body: JSON.stringify({ target_pct: targetPct }),
  });
}

// Floor layout — readable without a session (the anonymous dashboard
// renders it), so a plain fetch rather than serviceFetch.
export async function getLayout() {
  const res = await fetch('/api/layout');
  if (!res.ok) throw new ServiceApiError(`Request failed (${res.status})`, res.status);
  return res.json();
}

// Customer Demo Mode: chunked upload while recording. startDemoUpload()
// opens a session on the server (checks free disk space), each
// MediaRecorder chunk is PUT at its byte offset (a retried chunk that
// already arrived is ignored by the server), finalizeDemoUpload() makes it
// the demo. XMLHttpRequest with a timeout; resolves with the JSON answer,
// rejects with ServiceApiError("HTTP <status>: <server message>") for an
// HTTP error, or UploadNetworkError when no response arrived at all.
// A 401 does NOT log out here (unlike serviceFetch): the unsaved recording
// must stay on screen so it can be retried after logging in again.
export const DEMO_CHUNK_TIMEOUT_MS = 60 * 1000;
export const DEMO_FINALIZE_TIMEOUT_MS = 15 * 60 * 1000;

export class UploadNetworkError extends Error {
  constructor(kind) {
    super(kind === 'timeout' ? 'Upload timed out' : 'No response from the server');
    this.name = 'NetworkError';
    this.kind = kind; // 'network' | 'timeout'
  }
}

function demoRequest(method, url, body, timeoutMs) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(method, url);
    xhr.timeout = timeoutMs;
    if (body) xhr.setRequestHeader('Content-Type', 'video/webm');
    const { token } = get(auth);
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    xhr.onload = () => {
      let data = null;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        // non-JSON body (e.g. a proxy error page)
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data);
      else reject(new ServiceApiError(`HTTP ${xhr.status}: ${data?.detail ?? (xhr.statusText || 'request failed')}`, xhr.status));
    };
    xhr.onerror = () => reject(new UploadNetworkError('network'));
    xhr.ontimeout = () => reject(new UploadNetworkError('timeout'));
    xhr.send(body ?? null);
  });
}

/** -> { session_id }; HTTP 507 = not enough free disk space on the server. */
export function startDemoUpload() {
  return demoRequest('POST', '/api/demo/upload', null, DEMO_CHUNK_TIMEOUT_MS);
}

export function uploadDemoChunk(sessionId, offset, blob) {
  return demoRequest('PUT', `/api/demo/upload/${sessionId}?offset=${offset}`, blob, DEMO_CHUNK_TIMEOUT_MS);
}

/** -> the demo status. Can be retried after a failure (the file stays on the server). */
export function finalizeDemoUpload(sessionId, durationSeconds) {
  const url = `/api/demo/upload/${sessionId}/finalize?duration_seconds=${encodeURIComponent(durationSeconds.toFixed(2))}`;
  return demoRequest('POST', url, null, DEMO_FINALIZE_TIMEOUT_MS);
}

export function deleteDemoVideo() {
  return serviceFetch('/api/demo/video', { method: 'DELETE' });
}

export function setDemoSettings(showForAll) {
  return serviceFetch('/api/service/demo-settings', {
    method: 'PUT',
    body: JSON.stringify({ show_for_all: showForAll }),
  });
}

// State colours: GET is open (the dashboard loads them itself, see
// stateColors.js); saving is Service-only. "Reset all" is a save of the
// defaults the GET returned.
export function saveStateColors(colors) {
  return serviceFetch('/api/state-colors', {
    method: 'PUT',
    body: JSON.stringify(colors),
  });
}

export function saveLayout(layout) {
  return serviceFetch('/api/layout', {
    method: 'PUT',
    body: JSON.stringify(layout),
  });
}
