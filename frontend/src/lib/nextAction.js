import { translate } from './translations.js';
import { formatUnitNumber } from './format.js';

// Which machine the banner points at is decided ONCE, on the backend
// (production_pilot/priority.select_next_action, sent as the state
// payload's `next_action`): Error, then Hot, then Waiting, then Almost
// finished, each in saved priority order. This file only turns that pick
// into display text and a colour tier — it never re-ranks machines.
//
// kind -> [translation key, tier]. The tier picks the banner background
// (TopBar.svelte) and the NEXT badge accent (FryerTile.svelte).
const KINDS = {
  error: ['next_action_error', 'error'],
  switch_to_auto: ['next_action_switch_to_auto', 'hot'],
  load: ['next_action_load', 'load'],
  unload_soon: ['next_action_near_completion', 'near-completion'],
};

/**
 * Returns { text, tier, ip, allBaking }:
 *   - an actionable pick: "<no>: <action>" text, its tier, and the PLC's
 *     ip (so exactly that tile gets the NEXT badge);
 *   - nothing actionable: the dash, tier 'none', ip null — with
 *     allBaking true when every online machine is baking, so the banner
 *     shows a smiley instead of the dash.
 */
export function describeNextAction(nextAction, language) {
  const entry = nextAction ? KINDS[nextAction.kind] : undefined;
  if (entry) {
    const [key, tier] = entry;
    return {
      text: translate(language, key, { unit: formatUnitNumber(nextAction.unit_number) }),
      tier,
      ip: nextAction.ip,
      allBaking: false,
    };
  }
  return {
    text: translate(language, 'no_action'),
    tier: 'none',
    ip: null,
    allBaking: nextAction?.kind === 'all_baking',
  };
}
