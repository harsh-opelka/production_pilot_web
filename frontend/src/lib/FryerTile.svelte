<script>
  // Block-view only — the list view is a table (see MachineGroupSection.svelte
  // + MachineListRow.svelte), not a mode of this tile.
  import { formatElapsed, formatRemaining, formatUnitNumber, stateLabel } from './format.js';
  import { nowTick } from './stores.js';

  let { plc, language = 'en' } = $props();

  // "Fast fertig"/"Almost finished" override: reuses the HEATING amber
  // token for the tile background rather than a distinct colour — close
  // enough to "yellow" per the design note, and one fewer token to keep
  // in sync across themes. MachineState itself stays BAKING (see
  // production_pilot/priority.py's is_near_completion).
  let stateKey = $derived(plc.near_completion ? 'heating' : plc.state.toLowerCase());
  let label = $derived(stateLabel(plc, language));
  let unitLabel = $derived(formatUnitNumber(plc.unit_number));
  let showRemaining = $derived(plc.is_online && plc.state === 'BAKING' && plc.remaining_seconds != null);
  let remainingText = $derived(showRemaining ? formatRemaining(plc.remaining_seconds, language) : '');

  // Live elapsed-state timer for the non-baking, non-offline states —
  // ticks off the shared nowTick clock rather than its own interval, and
  // is derived from the server's state_entered_at so a reload resumes
  // from the true elapsed value instead of zero.
  const TIMER_STATES = new Set(['COLD', 'HEATING', 'READY', 'ERROR']);
  let showElapsed = $derived(!showRemaining && plc.is_online && TIMER_STATES.has(plc.state) && plc.state_entered_at != null);
  let elapsedText = $derived(showElapsed ? formatElapsed(($nowTick - Date.parse(plc.state_entered_at)) / 1000) : '');

  let tileStyle = $derived(
    plc.is_online ? `--tile-bg: var(--state-${stateKey}); --tile-fg: var(--state-${stateKey}-fg);` : '',
  );
</script>

<div class="tile" class:offline={!plc.is_online} style={tileStyle}>
  <div class="title">{unitLabel}</div>
  <div class="state">{label}</div>
  {#if plc.recipe}
    <div class="recipe">{plc.recipe}</div>
  {/if}
  {#if showRemaining}
    <div class="remaining">{remainingText}</div>
  {:else if showElapsed}
    <div class="remaining">{elapsedText}</div>
  {/if}
</div>

<style>
  .tile {
    --tile-bg: var(--offline-bg);
    --tile-fg: var(--offline-fg);
    background: var(--tile-bg);
    color: var(--tile-fg);
    border-radius: var(--radius);
    border: 2px solid transparent;
    height: clamp(13.75rem, 22vh, 16.25rem);
    padding: clamp(0.75rem, 1.5vw, 1.5rem);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: clamp(0.35rem, 0.8vh, 0.75rem);
    text-align: center;
  }

  .tile.offline {
    background: var(--offline-bg);
    color: var(--offline-fg);
    border: 2px dashed var(--offline-border);
    opacity: 0.5;
  }

  .title {
    font-size: var(--font-tile-title);
    font-weight: 700;
    line-height: 1.1;
  }

  .state {
    font-size: var(--font-tile-state);
    font-weight: 600;
  }

  .recipe {
    font-size: var(--font-tile-sub);
    opacity: 0.85;
  }

  .remaining {
    font-size: var(--font-tile-time);
    font-variant-numeric: tabular-nums;
  }
</style>
