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

export function stateLabel(plc, language) {
  if (!plc.is_online) return translate(language, 'status_offline');
  const key = `state_${plc.state.toLowerCase()}`;
  return translate(language, key);
}

export function formatHoursMinutes(seconds, language) {
  const total = Math.max(0, Math.round(seconds ?? 0));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  return translate(language, 'kpi_hm_format', { h, m });
}
