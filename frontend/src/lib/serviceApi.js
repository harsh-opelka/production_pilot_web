import { get } from 'svelte/store';
import { auth } from './stores.js';

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
 * still authorized (see App.svelte's $effect on $auth.token).
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
}

export function logout() {
  auth.set({ token: null, level: null });
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

export function getDailySummary(date) {
  return serviceFetch(`/api/stats/daily-summary?date=${encodeURIComponent(date)}`);
}

export function getRangeSummary(start, end) {
  return serviceFetch(`/api/stats/range-summary?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`);
}
