import { get } from 'svelte/store';
import { serviceToken, serviceSessionExpired } from './stores.js';

export class ServiceApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

/**
 * Fetch wrapper for every /api/service/* call except login. Attaches the
 * current token, and on a 401 clears it — the session is gone (expired
 * or the server restarted), so the UI must drop back to the login
 * prompt rather than keep pretending it's still authenticated.
 */
async function serviceFetch(path, options = {}) {
  const token = get(serviceToken);
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
    // Only a *previously valid* token expiring counts as a session
    // timeout — login() itself hits this same 401 path on a wrong
    // password, while there was never a token to begin with.
    if (get(serviceToken) !== null) serviceSessionExpired.set(true);
    serviceToken.set(null);
    throw new ServiceApiError(data?.detail ?? 'Not authenticated', 401);
  }

  if (!res.ok) {
    throw new ServiceApiError(data?.detail ?? `Request failed (${res.status})`, res.status);
  }

  return data;
}

export async function login(password) {
  const data = await serviceFetch('/api/service/login', {
    method: 'POST',
    body: JSON.stringify({ password }),
  });
  serviceToken.set(data.token);
}

export function logout() {
  serviceToken.set(null);
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
