import { translate } from './translations.js';

export function formatRemaining(seconds, language) {
  const total = Math.max(0, seconds ?? 0);
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  return translate(language, 'remaining_time_format', { mins, secs });
}

export function formatUnitLabel(unitNumber, language) {
  return `${translate(language, 'unit_fryer')} ${unitNumber}`;
}

// Plain unit number, no "Machine"/"Maschine" word — used only for the
// primary tile/row label in block and list view (see FryerTile.svelte,
// MachineListRow.svelte). Everywhere else (next-action text, charts,
// Statistics) keeps the word via formatUnitLabel for context.
export function formatUnitNumber(unitNumber) {
  return `${unitNumber}`;
}

export function stateLabel(plc, language) {
  if (!plc.is_online) return translate(language, 'status_offline');
  // "Fast fertig"/"Almost finished" display override — MachineState stays
  // BAKING internally (see production_pilot/priority.py's
  // is_near_completion), only the label/colour shown here changes.
  if (plc.near_completion) return translate(language, 'state_near_completion');
  const key = `state_${plc.state.toLowerCase()}`;
  return translate(language, key);
}

// Live elapsed-time timer (COLD/HEATING/READY/ERROR tiles) — counts UP
// from a server-provided state_entered_at timestamp. MM:SS under an hour,
// HH:MM:SS beyond it.
export function formatElapsed(seconds) {
  const total = Math.max(0, Math.floor(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n) => String(n).padStart(2, '0');
  return h > 0 ? `${pad(h)}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}

export function formatHoursMinutes(seconds, language) {
  const total = Math.max(0, Math.round(seconds ?? 0));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  return translate(language, 'kpi_hm_format', { h, m });
}

export function todayLocalDate() {
  const d = new Date();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${mm}-${dd}`;
}
