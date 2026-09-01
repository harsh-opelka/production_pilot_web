<script>
  // Block-view only — the list view is a table (see MachineGroupSection.svelte
  // + MachineListRow.svelte), not a mode of this tile.
  import { formatRemaining, formatUnitLabel, stateLabel } from './format.js';

  let { plc, language = 'en' } = $props();

  let stateKey = $derived(plc.state.toLowerCase());
  let label = $derived(stateLabel(plc, language));
  let unitLabel = $derived(formatUnitLabel(plc.unit_number, language));
  let showRemaining = $derived(plc.is_online && plc.state === 'BAKING' && plc.remaining_seconds != null);
  let remainingText = $derived(showRemaining ? formatRemaining(plc.remaining_seconds, language) : '');
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
