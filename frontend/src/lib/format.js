import { translate } from './translations.js';

// Single wordy duration formatter shared by every state timer (Baking's
// countdown and the live elapsed timers for Cold/Heating/Waiting/Error) —
// "X Min. Y Sek." under an hour, "X Std. Y Min." once it reaches an hour,
// so long-running states don't degrade into an unbroken run of minutes.
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
