<script>
  import { formatRemaining, formatUnitLabel, stateLabel } from './format.js';

  let { plc, mode = 'block', language = 'en' } = $props();

  let stateKey = $derived(plc.state.toLowerCase());
  let label = $derived(stateLabel(plc, language));
  let unitLabel = $derived(formatUnitLabel(plc.unit_number, language));
  let showRemaining = $derived(plc.is_online && plc.state === 'BAKING' && plc.remaining_seconds != null);
  let remainingText = $derived(showRemaining ? formatRemaining(plc.remaining_seconds, language) : '');
  let tileStyle = $derived(
    plc.is_online ? `--tile-bg: var(--state-${stateKey}); --tile-fg: var(--state-${stateKey}-fg);` : '',
  );
</script>

<div class="tile {mode}" class:offline={!plc.is_online} style={tileStyle}>
  <div class="title">{unitLabel}</div>
  <div class="ip">{plc.ip}</div>
  <div class="state">{label}</div>
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
  }

  .tile.offline {
    background: var(--offline-bg);
    color: var(--offline-fg);
    border: 2px dashed var(--offline-border);
    opacity: 0.5;
  }

  .tile.block {
    height: clamp(220px, 22vh, 260px);
    padding: clamp(0.75rem, 1.5vw, 1.5rem);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: clamp(0.35rem, 0.8vh, 0.75rem);
    text-align: center;
  }

  .tile.list {
    padding: clamp(0.5rem, 1vh, 1rem) clamp(0.9rem, 1.5vw, 1.5rem);
    display: flex;
    align-items: center;
    gap: clamp(1rem, 2vw, 2.5rem);
  }

  .title {
    font-size: var(--font-tile-title);
    font-weight: 700;
    line-height: 1.1;
  }

  .tile.list .title {
    min-width: 8ch;
    text-align: left;
  }

  .ip {
    font-size: var(--font-tile-sub);
    opacity: 0.85;
  }

  .tile.list .ip {
    min-width: 12ch;
    font-family: ui-monospace, Consolas, monospace;
  }

  .state {
    font-size: var(--font-tile-state);
    font-weight: 600;
  }

  .tile.list .state {
    min-width: 10ch;
    text-align: left;
  }

  .remaining {
    font-size: var(--font-tile-time);
    font-variant-numeric: tabular-nums;
  }

  .tile.list .remaining {
    margin-left: auto;
  }
</style>
