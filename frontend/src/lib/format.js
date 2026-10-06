import { translate } from './translations.js';

// Single wordy duration formatter shared by every state timer (Baking's
// countdown and the live elapsed timers for Cold/Heating/Waiting/Error) —
// "X Min Y Sek" under an hour, "X Std Y Min" once it reaches an hour, so
// long-running states don't degrade into an unbroken run of minutes.
// Abbreviations are deliberately period-free (translations.js/
// translations_de.json's duration_ms_format/duration_hm_format) — not
// "Min." / "Sek." / "Std." — per spec.
export function formatDuration(seconds, language) {
  const total = Math.max(0, Math.floor(seconds ?? 0));
  if (total >= 3600) {
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    return translate(language, 'duration_hm_format', { h, m });
  }
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  return translate(language, 'duration_ms_format', { mins, secs });
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

// Shown wherever a PLC value is unknown — never an invented number.
export const BLANK = '—';

// "29 / 20 °C" (current / target, whole degrees) for the tile and list
// view. A missing side shows as "—"; both missing collapses to just "—".
export function formatTemperature(current, target) {
  if (current == null && target == null) return BLANK;
  const whole = (v) => (v == null ? BLANK : String(Math.round(v)));
  return `${whole(current)} / ${whole(target)} °C`;
}

// Heating tile "fill level" (FryerTile.svelte): how far the oil has come
// towards its target, 0..1. null = no fill (a value missing, or no usable
// target) — never a guessed level.
export function heatingFillLevel(current, target) {
  if (current == null || target == null || !(target > 0)) return null;
  return Math.min(1, Math.max(0, current / target));
}

export function formatRecipe(recipeName) {
  return recipeName ? recipeName : BLANK;
}

export function formatHoursMinutes(seconds, language) {
  const total = Math.max(0, Math.round(seconds ?? 0));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  return translate(language, 'kpi_hm_format', { h, m });
}

// Picks a display unit for a chart axis from the max value (in seconds)
// in its dataset, so short durations don't read as "0,05 Minutes" and
// long ones don't read as an unbroken run of three-digit minutes — see
// Statistics.svelte's charts. Boundaries: <2min -> seconds, 2min-3h ->
// minutes, >3h -> hours.
export function pickDurationUnit(maxSeconds) {
  if (maxSeconds < 120) return { divisor: 1, labelKey: 'stats_axis_seconds' };
  if (maxSeconds <= 3 * 3600) return { divisor: 60, labelKey: 'stats_axis_minutes' };
  return { divisor: 3600, labelKey: 'stats_axis_hours' };
}

export function todayLocalDate() {
  const d = new Date();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${mm}-${dd}`;
}
