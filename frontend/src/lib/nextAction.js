import { translate } from './translations.js';
import { formatCountdown, formatUnitNumber } from './format.js';

// Which machine the banner points at is decided ONCE, on the backend
// (production_pilot/priority.select_next_action, sent as the state
// payload's `next_action`): Error, then Standby (shown as Cold, Hot or
// Standby — all "Switch to Auto"), then Waiting, then Almost finished,
// each in saved priority order. This file only turns that pick into
// display text — it never re-ranks machines. The banner and the NEXT
// badge look the same for every action (TopBar.svelte / FryerTile.svelte);
// only the text changes.
//
// kind -> translation key of the action text (without the machine number,
// which the banner shows in its own badge).
const KINDS = {
  error: 'next_action_error',
  switch_to_auto: 'next_action_switch_to_auto',
  load: 'next_action_load',
  unload_soon: 'next_action_near_completion',
};

/**
 * `elapsedSeconds`: time since this payload arrived (see websocket.js
 * received_at) — only used to count the New Cycle "Wait" down between
 * server messages; the remaining time itself always comes from the server.
 *
 * Returns { unit, action, text, ip, nothingToDo, next }:
 *   - an actionable pick: the machine number (`unit`, for the banner's
 *     badge), the translated `action`, `text` = "<no>: <action>" (for
 *     screen readers / tooltips), and the PLC's ip (so exactly that tile
 *     gets the NEXT badge);
 *   - nothing actionable: unit and ip null (no NEXT badge), text/action
 *     the dash — with nothingToDo true when machines are online but
 *     there's nothing to do right now (all baking, or every Waiting
 *     machine held back by a Heating machine in its group), so the banner
 *     shows the smiley instead of the dash;
 *   - New Cycle start delay (kind "wait"): action "Wait m:ss" counting
 *     down, no machine number and ip null (no NEXT badge), and `next` =
 *     "Next: Machine <n>" (the machine asked for once the delay is over).
 * `next` is null for every other kind.
 */
export function describeNextAction(nextAction, language, elapsedSeconds = 0) {
  if (nextAction?.kind === 'wait') {
    const remaining = Math.max(0, (nextAction.wait_remaining_seconds ?? 0) - Math.floor(Math.max(0, elapsedSeconds)));
    const action = translate(language, 'next_action_wait', { time: formatCountdown(remaining) });
    const next =
      nextAction.next_unit_number != null
        ? translate(language, 'next_action_wait_next', { unit: formatUnitNumber(nextAction.next_unit_number) })
        : null;
    return { unit: null, action, text: action, ip: null, nothingToDo: false, next };
  }
  const key = nextAction ? KINDS[nextAction.kind] : undefined;
  if (key) {
    const unit = formatUnitNumber(nextAction.unit_number);
    const action = translate(language, key);
    return { unit, action, text: `${unit}: ${action}`, ip: nextAction.ip, nothingToDo: false, next: null };
  }
  const dash = translate(language, 'no_action');
  return {
    unit: null,
    action: dash,
    text: dash,
    ip: null,
    nothingToDo: nextAction?.kind === 'nothing_to_do',
    next: null,
  };
}
