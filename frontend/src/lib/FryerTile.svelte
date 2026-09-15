<script>
  // Block-view only — the list view is a table (see MachineGroupSection.svelte
  // + MachineListRow.svelte), not a mode of this tile.
  import { formatDuration, formatUnitNumber, stateLabel } from './format.js';
  import { nowTick } from './stores.js';
  import { translate } from './translations.js';

  // isNext/tier: whether this tile is the single machine the Next Action
  // banner currently points at, and which tier drove that pick (see
  // TopBar.svelte + nextAction.js — this never recomputes priority itself,
  // just mirrors the same computeNextAction() result the caller already
  // has). tier is only meaningful when isNext is true.
  let { plc, language = 'en', isNext = false, tier = null } = $props();

  // "Fast fertig"/"Almost finished" override: its own bright warning-
  // yellow token (--state-near-completion), distinct from HEATING's
  // amber-orange — see app.css. MachineState itself stays BAKING (see
  // production_pilot/priority.py's is_near_completion).
  let stateKey = $derived(plc.near_completion ? 'near-completion' : plc.state.toLowerCase());
  let label = $derived(stateLabel(plc, language));
  let unitLabel = $derived(formatUnitNumber(plc.unit_number));
  let showRemaining = $derived(plc.is_online && plc.state === 'BAKING' && plc.remaining_seconds != null);
  let remainingText = $derived(showRemaining ? formatDuration(plc.remaining_seconds, language) : '');

  // Live elapsed-state timer for the non-baking, non-offline states —
  // ticks off the shared nowTick clock rather than its own interval, and
  // is derived from the server's state_entered_at so a reload resumes
  // from the true elapsed value instead of zero.
  const TIMER_STATES = new Set(['COLD', 'HEATING', 'READY', 'ERROR']);
  let showElapsed = $derived(!showRemaining && plc.is_online && TIMER_STATES.has(plc.state) && plc.state_entered_at != null);
  let elapsedText = $derived(showElapsed ? formatDuration(($nowTick - Date.parse(plc.state_entered_at)) / 1000, language) : '');

  let tileStyle = $derived(
    plc.is_online ? `--tile-bg: var(--state-${stateKey}); --tile-fg: var(--state-${stateKey}-fg);` : '',
  );
  // Only meaningful (and only applied) while isNext is true — see .tile.next-priority.tier-* below.
  let tierClass = $derived(isNext && tier ? `tier-${tier}` : '');
</script>

<div class="tile {tierClass}" class:offline={!plc.is_online} class:next-priority={isNext} style={tileStyle}>
  {#if isNext}
    <div class="next-badge">{translate(language, 'tile_next_badge')}</div>
  {/if}
  <div class="unit">{unitLabel}</div>
  <div class="middle">
    <div class="state">{label}</div>
    {#if showRemaining}
      <div class="time">{remainingText}</div>
    {:else if showElapsed}
      <div class="time">{elapsedText}</div>
    {/if}
  </div>
  <div class="recipe">{plc.recipe ?? ''}</div>
</div>

<style>
  /* Grid rows (not a single centered flex stack): unit pinned to the top,
     recipe pinned to the bottom, state+time centered in the flexible
     middle row — see .middle. The recipe cell is always rendered (even
     when empty) so its reserved bottom row keeps tile height/layout
     identical whether or not a recipe is set, across every state colour. */
  .tile {
    --tile-bg: var(--offline-bg);
    --tile-fg: var(--offline-fg);
    position: relative;
    background: var(--tile-bg);
    color: var(--tile-fg);
    border-radius: var(--tile-radius);
    /* No visible border on colored state tiles — --tile-shadow (theme-
       dependent, see app.css) provides the separation from --bg-app and
       neighbouring tiles instead: a soft outer drop shadow plus a faint
       inset top-edge highlight ("Option A" subtle depth) — both flat
       box-shadow layers, deliberately no gradient/gloss overlay, so the
       state colour itself stays exactly as flat and solid as before. */
    border: none;
    box-shadow: var(--tile-shadow);
    height: clamp(13.75rem, 22vh, 16.25rem);
    padding: clamp(0.75rem, 1.5vw, 1.5rem);
    display: grid;
    grid-template-rows: auto 1fr auto;
    justify-items: center;
    text-align: center;
  }

  .tile.offline {
    background: var(--offline-bg);
    color: var(--offline-fg);
    border: 2px dashed var(--offline-border);
    opacity: 0.5;
  }

  /* Top-priority highlight — the one tile matching the Next Action banner
     (see FryerTile's isNext/tier props + Dashboard.svelte). Coloured
     border + soft halo, using the exact same colour as the banner's
     tier-* background (TopBar.svelte) so the two always agree. Only ever
     one tile at a time carries this, since isNext is derived from the
     single computeNextAction() result the whole dashboard shares. */
  .tile.next-priority {
    border: 3px solid var(--tile-accent, transparent);
    box-shadow:
      var(--tile-shadow),
      0 0 0 6px var(--tile-accent-glow, transparent);
  }

  .tile.next-priority.tier-error {
    --tile-accent: var(--state-error);
    --tile-accent-glow: rgba(220, 38, 38, 0.35);
  }

  .tile.next-priority.tier-near-completion {
    --tile-accent: var(--state-near-completion);
    --tile-accent-glow: rgba(250, 204, 21, 0.4);
  }

  .tile.next-priority.tier-ready {
    --tile-accent: var(--opelka-blue);
    --tile-accent-glow: rgba(5, 52, 108, 0.35);
  }

  .next-badge {
    position: absolute;
    top: -0.6rem;
    left: -0.6rem;
    padding: 0.15rem 0.6rem;
    border-radius: 999px;
    background: var(--tile-accent, var(--opelka-blue));
    color: #ffffff;
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.02em;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.35);
    z-index: 1;
  }

  .unit {
    align-self: start;
    font-size: var(--font-tile-unit);
    font-weight: 400;
    line-height: 1.1;
  }

  .middle {
    align-self: center;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: clamp(0.15rem, 0.4vh, 0.35rem);
  }

  .state {
    font-size: var(--font-tile-state);
    font-weight: 700;
  }

  .time {
    font-size: var(--font-tile-time);
    font-weight: 700;
    font-variant-numeric: tabular-nums;
  }

  .recipe {
    align-self: end;
    min-height: 1em;
    font-size: var(--font-tile-sub);
    font-weight: 400;
    opacity: 0.85;
  }
</style>
