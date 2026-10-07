import { writable, get } from 'svelte/store';

// Machine-state colours, Service-configurable (StateColorsCard.svelte).
// The backend owns the values AND the defaults (production_pilot/
// state_colors.py, GET /api/state-colors) — nothing here hard-codes a
// state colour. applyStateColors() turns them into CSS variables on
// <html>, so tiles, legend dots, list view, Statistics and the Service
// preview all read the same source:
//   --state-<css>     the background
//   --state-<css>-fg  white or dark text, picked from its luminance

// Backend slot key -> CSS variable suffix + legend label key, in the
// order the Service tab lists them.
export const STATE_COLOR_SLOTS = [
  { key: 'waiting', css: 'waiting', labelKey: 'state_waiting' },
  { key: 'baking', css: 'baking', labelKey: 'state_baking' },
  { key: 'near_completion', css: 'near-completion', labelKey: 'state_near_completion' },
  { key: 'heating', css: 'heating', labelKey: 'state_heating' },
  { key: 'hot', css: 'hot', labelKey: 'state_hot' },
  { key: 'cold', css: 'cold', labelKey: 'state_cold' },
  { key: 'blocked', css: 'blocked', labelKey: 'state_blocked' },
  { key: 'error', css: 'error', labelKey: 'state_error' },
  { key: 'standby', css: 'standby', labelKey: 'service_colors_standby_unknown' },
];

export const TEXT_LIGHT = '#FFFFFF';
export const TEXT_DARK = '#1C1C1C';
// WCAG AA for normal text.
export const MIN_CONTRAST = 4.5;
// Two state colours closer than this (CIE76 ΔE in Lab space) are hard to
// tell apart on a TV across the hall -> warning in the Service tab. ~18 is
// "clearly the same family": green vs a darker green (17.6) warns, the
// default Cold grey vs Blocked slate (18.7) doesn't.
export const SIMILAR_COLOR_DELTA_E = 18;
// Pairs that are meant to look alike (told apart by something else) and
// so never warn: the Standby/Unknown fallback is Cold's grey on purpose,
// distinguished by its lighter border.
const SIMILARITY_EXEMPT = [['cold', 'standby']];

const HEX_RE = /^#(?:[0-9a-f]{3}|[0-9a-f]{6})$/i;

/** '#RGB' / '#RRGGBB' (any case, spaces trimmed) -> '#RRGGBB' uppercase, or null if invalid. */
export function normalizeHex(value) {
  if (typeof value !== 'string') return null;
  const v = value.trim();
  if (!HEX_RE.test(v)) return null;
  const digits = v.length === 4 ? [...v.slice(1)].map((c) => c + c).join('') : v.slice(1);
  return `#${digits.toUpperCase()}`;
}

export function hexToRgb(hex) {
  const n = normalizeHex(hex);
  return [1, 3, 5].map((i) => parseInt(n.slice(i, i + 2), 16));
}

export function rgbToHex([r, g, b]) {
  return `#${[r, g, b].map((c) => Math.round(Math.min(255, Math.max(0, c))).toString(16).padStart(2, '0')).join('')}`.toUpperCase();
}

function linear(c) {
  const s = c / 255;
  return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}

/** WCAG relative luminance, 0 (black) .. 1 (white). */
export function relativeLuminance(hex) {
  const [r, g, b] = hexToRgb(hex).map(linear);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrastRatio(a, b) {
  const [hi, lo] = [relativeLuminance(a), relativeLuminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/** The more readable of white / dark text on `bg`, with its contrast ratio. */
export function bestText(bg) {
  const light = contrastRatio(bg, TEXT_LIGHT);
  const dark = contrastRatio(bg, TEXT_DARK);
  return light >= dark ? { color: TEXT_LIGHT, ratio: light } : { color: TEXT_DARK, ratio: dark };
}

export function bestTextColor(bg) {
  return bestText(bg).color;
}

function toLab(hex) {
  const [r, g, b] = hexToRgb(hex).map(linear);
  const x = (r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.95047;
  const y = r * 0.2126 + g * 0.7152 + b * 0.0722;
  const z = (r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.08883;
  const f = (t) => (t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116);
  return [116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))];
}

/** CIE76 colour difference (ΔE) — 0 = identical, ~2.3 = just noticeable. */
export function colorDistance(a, b) {
  const la = toLab(a);
  const lb = toLab(b);
  return Math.hypot(la[0] - lb[0], la[1] - lb[1], la[2] - lb[2]);
}

/** [[keyA, keyB], ...] of slots whose colours are closer than SIMILAR_COLOR_DELTA_E. */
export function findSimilarPairs(colors) {
  const keys = STATE_COLOR_SLOTS.map((s) => s.key).filter((k) => normalizeHex(colors[k]));
  const exempt = (a, b) => SIMILARITY_EXEMPT.some(([x, y]) => (x === a && y === b) || (x === b && y === a));
  const pairs = [];
  keys.forEach((a, i) => {
    for (const b of keys.slice(i + 1)) {
      if (!exempt(a, b) && colorDistance(colors[a], colors[b]) < SIMILAR_COLOR_DELTA_E) pairs.push([a, b]);
    }
  });
  return pairs;
}

// HSV <-> RGB for the free picker (h 0..360, s/v 0..1).
export function hexToHsv(hex) {
  const [r, g, b] = hexToRgb(hex).map((c) => c / 255);
  const max = Math.max(r, g, b);
  const d = max - Math.min(r, g, b);
  let h = 0;
  if (d) {
    if (max === r) h = ((g - b) / d) % 6;
    else if (max === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    h = (h * 60 + 360) % 360;
  }
  return { h, s: max ? d / max : 0, v: max };
}

export function hsvToHex({ h, s, v }) {
  const c = v * s;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = v - c;
  const [r, g, b] =
    h < 60 ? [c, x, 0] : h < 120 ? [x, c, 0] : h < 180 ? [0, c, x] : h < 240 ? [0, x, c] : h < 300 ? [x, 0, c] : [c, 0, x];
  return rgbToHex([(r + m) * 255, (g + m) * 255, (b + m) * 255]);
}

/** CSS custom properties for a {slot: hex} map — also used for the Service preview tiles. */
export function stateColorVars(colors) {
  const vars = {};
  for (const { key, css } of STATE_COLOR_SLOTS) {
    const hex = normalizeHex(colors?.[key]);
    if (!hex) continue;
    vars[`--state-${css}`] = hex;
    vars[`--state-${css}-fg`] = bestTextColor(hex);
  }
  return vars;
}

// { colors, defaults, version } as last loaded from the backend.
export const stateColors = writable({ colors: null, defaults: null, version: null });

export function applyStateColors(payload) {
  const root = document.documentElement;
  for (const [name, value] of Object.entries(stateColorVars(payload.colors))) root.style.setProperty(name, value);
  stateColors.set({ colors: payload.colors, defaults: payload.defaults, version: payload.version });
}

/** Fetches GET /api/state-colors and applies it. Never throws (the next
 *  state payload's colors_version triggers a retry — see websocket.js). */
let inflight = null;
export function loadStateColors() {
  inflight ??= (async () => {
    try {
      const res = await fetch('/api/state-colors');
      if (res.ok) applyStateColors(await res.json());
    } catch {
      // Server not reachable yet — retried on the next state message.
    } finally {
      inflight = null;
    }
  })();
  return inflight;
}

/** Called with every state payload: re-fetch when the backend's colours changed. */
export function syncStateColors(colorsVersion) {
  if (colorsVersion && colorsVersion !== get(stateColors).version) loadStateColors();
}
