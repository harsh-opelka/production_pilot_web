import { translate } from './translations.js';
import { formatUnitNumber } from './format.js';

const isError = (plc) => plc.is_online && plc.state === 'ERROR';
// "Almost Finished" is a display-state override the backend computes
// (see production_pilot/priority.is_near_completion, sent as the
// near_completion flag) — MachineState itself stays BAKING underneath,
// so this checks the override flag rather than re-deriving the
// remaining_seconds threshold locally. Same flag FryerTile.svelte uses
// for the tile's yellow override, so the two can't drift apart.
const isNearDoneBaking = (plc) => plc.is_online && plc.near_completion === true;
const isReady = (plc) => plc.is_online && plc.state === 'READY';

// Combined "{unit}: <action>" text for the two-tier Next Action box (see
// TopBar.svelte) — e.g. "3: Load" / "3: Beladen".
function buildMessage(key, plc, language) {
  return translate(language, key, { unit: formatUnitNumber(plc.unit_number) });
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
 * the message ('error' | 'near-completion' | 'ready' | 'none'), purely so
 * the caller can pick a display colour; it does not affect which message
 * gets chosen. Note there is no plain "baking" tier — isNearDoneBaking is
 * the only Baking-related candidate check, so this tier always means the
 * "Almost Finished" override, never ordinary Baking (see TopBar.svelte's
 * .tier-near-completion, which reuses the exact same yellow as the tile).
 */
export function computeNextAction(groups, language) {
  const candidates = groups.filter((g) => g.plcs.length > 0).map((g) => ({ group: g, plc: g.plcs[0] }));

  const errorHit = candidates.find((c) => isError(c.plc));
  if (errorHit) {
    return { text: buildMessage('next_action_error', errorHit.plc, language), tier: 'error' };
  }

  const bakingHit = candidates.find((c) => isNearDoneBaking(c.plc));
  if (bakingHit) {
    return { text: buildMessage('next_action_near_completion', bakingHit.plc, language), tier: 'near-completion' };
  }

  const readyHit = candidates.find((c) => isReady(c.plc));
  if (readyHit) {
    return { text: buildMessage('next_action_load', readyHit.plc, language), tier: 'ready' };
  }

  for (const group of groups) {
    const readyPlc = group.plcs.find(isReady);
    if (readyPlc) return { text: buildMessage('next_action_load', readyPlc, language), tier: 'ready' };
  }

  return { text: translate(language, 'no_action'), tier: 'none' };
}
