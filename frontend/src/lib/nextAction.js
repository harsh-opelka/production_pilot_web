import { translate } from './translations.js';
import { formatUnitNumber } from './format.js';

// Which machine the banner points at is decided ONCE, on the backend
// (production_pilot/priority.select_next_action, sent as the state
// payload's `next_action`): Error, then Standby (shown as Cold, Hot or
// Standby — all "Switch to Auto"), then Waiting, then Almost finished,
// each in saved priority order. This file only turns that pick
// into display text and a colour tier — it never re-ranks machines.
//
// kind -> [translation key, tier]. The tier picks the banner background
// (TopBar.svelte) and the NEXT ring/badge colour (FryerTile.svelte), and
// always matches the chosen machine's tile colour — so "Switch to Auto"
// has no fixed tier: it follows the machine's state (see tierFor).
const KINDS = {
  error: ['next_action_error', 'error'],
  switch_to_auto: ['next_action_switch_to_auto', null],
  load: ['next_action_load', 'load'],
  unload_soon: ['next_action_near_completion', 'near-completion'],
};

// Switch to Auto: yellow only for a Hot machine; Cold and plain Standby
// (temperature unreadable) are both grey tiles, so grey.
function tierFor(kindTier, state) {
  if (kindTier) return kindTier;
  return state === 'HOT' ? 'hot' : 'cold';
}

/**
 * Returns { text, tier, ip, nothingToDo }:
 *   - an actionable pick: "<no>: <action>" text, its tier, and the PLC's
 *     ip (so exactly that tile gets the NEXT badge);
 *   - nothing actionable: the dash, tier 'none', ip null (no NEXT badge)
 *     — with nothingToDo true when machines are online but there's
 *     nothing to do right now (all baking, or every Waiting machine held
 *     back by a Heating machine in its group), so the banner shows the
 *     smiley instead of the dash.
 */
export function describeNextAction(nextAction, language) {
  const entry = nextAction ? KINDS[nextAction.kind] : undefined;
  if (entry) {
    const [key, kindTier] = entry;
    return {
      text: translate(language, key, { unit: formatUnitNumber(nextAction.unit_number) }),
      tier: tierFor(kindTier, nextAction.state),
      ip: nextAction.ip,
      nothingToDo: false,
    };
  }
  return {
    text: translate(language, 'no_action'),
    tier: 'none',
    ip: null,
    nothingToDo: nextAction?.kind === 'nothing_to_do',
  };
}
