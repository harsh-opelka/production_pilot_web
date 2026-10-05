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
 * Walks every group's plcs in the order the backend sent them (already
 * sorted by priority.calculate_priority: Error, then Ready/Baking/Almost
 * finished by saved priority, then Heating, then Cold/Offline) and picks
 * the first machine that is actionable NOW, in this precedence:
 *   1. the first Error machine;
 *   2. otherwise the first Ready machine — any Baking / Almost-finished
 *      machine ranked above it is skipped, it has nothing to do yet;
 *   3. only if nothing is in Error or Ready, the first Almost-finished
 *      machine ("Unload soon").
 * So an Almost-finished tile keeps its yellow styling but never takes the
 * banner (or the NEXT badge) while any Ready machine exists.
 *
 * Returns { text, tier, ip } — tier identifies which precedence rule
 * produced the message ('error' | 'near-completion' | 'ready' | 'none'),
 * purely so the caller can pick a display colour; it does not affect which
 * message gets chosen. Note there is no plain "baking" tier —
 * isNearDoneBaking is the only Baking-related candidate check, so this
 * tier always means the "Almost Finished" override, never ordinary Baking
 * (see TopBar.svelte's .tier-near-completion, which reuses the exact same
 * yellow as the tile). `ip` is the matched plc's identity (or null for
 * 'none'), so callers can highlight the exact tile this message is about
 * (see FryerTile.svelte's isNext prop) without re-deriving priority.
 */
export function computeNextAction(groups, language) {
  const plcs = groups.flatMap((g) => g.plcs);

  const errorPlc = plcs.find(isError);
  if (errorPlc) {
    return { text: buildMessage('next_action_error', errorPlc, language), tier: 'error', ip: errorPlc.ip };
  }

  const readyPlc = plcs.find(isReady);
  if (readyPlc) {
    return { text: buildMessage('next_action_load', readyPlc, language), tier: 'ready', ip: readyPlc.ip };
  }

  const nearDonePlc = plcs.find(isNearDoneBaking);
  if (nearDonePlc) {
    return {
      text: buildMessage('next_action_near_completion', nearDonePlc, language),
      tier: 'near-completion',
      ip: nearDonePlc.ip,
    };
  }

  return { text: translate(language, 'no_action'), tier: 'none', ip: null };
}
