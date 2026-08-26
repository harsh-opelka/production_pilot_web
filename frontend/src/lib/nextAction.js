import { translate } from './translations.js';
import { formatUnitLabel } from './format.js';

// Mirrors production_pilot/priority.py's NEAR_COMPLETION_THRESHOLD_SECONDS.
const NEAR_COMPLETION_THRESHOLD_SECONDS = 30;

const isError = (plc) => plc.is_online && plc.state === 'ERROR';
const isNearDoneBaking = (plc) =>
  plc.is_online &&
  plc.state === 'BAKING' &&
  plc.remaining_seconds != null &&
  plc.remaining_seconds < NEAR_COMPLETION_THRESHOLD_SECONDS;
const isReady = (plc) => plc.is_online && plc.state === 'READY';

function buildMessage(key, group, plc, language) {
  return translate(language, key, {
    group: group.name,
    fryer: formatUnitLabel(plc.unit_number, language),
  });
}

/**
 * Mirrors V1: take each group's first (highest-priority, already sorted
 * by the backend) fryer as that group's candidate, then pick the most
 * urgent candidate by tier (Error > near-done Baking > Ready). If no
 * candidate qualifies (all candidates are Heating/Cold/Offline/normal
 * Baking), fall back to the first READY fryer anywhere — it may not be
 * its own group's first slot, e.g. a normal-baking machine with time to
 * spare can outrank a READY sibling within the same group.
 *
 * Returns { text, tier } — tier identifies which precedence rule produced
 * the message ('error' | 'baking' | 'ready' | 'none'), purely so the
 * caller can pick a display colour; it does not affect which message
 * gets chosen.
 */
export function computeNextAction(groups, language) {
  const candidates = groups.filter((g) => g.plcs.length > 0).map((g) => ({ group: g, plc: g.plcs[0] }));

  const errorHit = candidates.find((c) => isError(c.plc));
  if (errorHit) {
    return { text: buildMessage('next_action_error', errorHit.group, errorHit.plc, language), tier: 'error' };
  }

  const bakingHit = candidates.find((c) => isNearDoneBaking(c.plc));
  if (bakingHit) {
    return { text: buildMessage('next_action_unload', bakingHit.group, bakingHit.plc, language), tier: 'baking' };
  }

  const readyHit = candidates.find((c) => isReady(c.plc));
  if (readyHit) {
    return { text: buildMessage('next_action_load', readyHit.group, readyHit.plc, language), tier: 'ready' };
  }

  for (const group of groups) {
    const readyPlc = group.plcs.find(isReady);
    if (readyPlc) return { text: buildMessage('next_action_load', group, readyPlc, language), tier: 'ready' };
  }

  return { text: translate(language, 'no_action'), tier: 'none' };
}
