<script>
  // Block-view only — the list view is a table (see MachineGroupSection.svelte
  // + MachineListRow.svelte), not a mode of this tile.
  import { formatDuration, formatUnitNumber, stateLabel } from './format.js';
  import { nowTick } from './stores.js';

  let { plc, language = 'en' } = $props();

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
</script>

<div class="tile" class:offline={!plc.is_online} style={tileStyle}>
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
    background: var(--tile-bg);
    color: var(--tile-fg);
    border-radius: var(--radius);
    border: 2px solid transparent;
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
