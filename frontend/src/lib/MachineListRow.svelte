<script>
  import { formatElapsed, formatRemaining, formatUnitNumber, stateLabel } from './format.js';
  import { translate } from './translations.js';
  import { nowTick } from './stores.js';

  let { plc, language = 'en', productivityPct = null } = $props();

  // Same "Fast fertig"/"Almost finished" colour override as FryerTile.svelte.
  let stateKey = $derived(plc.near_completion ? 'heating' : plc.state.toLowerCase());
  let label = $derived(stateLabel(plc, language));
  let unitLabel = $derived(formatUnitNumber(plc.unit_number));
  let dotStyle = $derived(plc.is_online ? `background: var(--state-${stateKey});` : `background: var(--offline-border);`);
  let showRemaining = $derived(plc.is_online && plc.state === 'BAKING' && plc.remaining_seconds != null);

  const TIMER_STATES = new Set(['COLD', 'HEATING', 'READY', 'ERROR']);
  let showElapsed = $derived(!showRemaining && plc.is_online && TIMER_STATES.has(plc.state) && plc.state_entered_at != null);

  let timeText = $derived(
    showRemaining
      ? formatRemaining(plc.remaining_seconds, language)
      : showElapsed
        ? formatElapsed(($nowTick - Date.parse(plc.state_entered_at)) / 1000)
        : translate(language, 'no_action'),
  );
  let productivityText = $derived(productivityPct != null ? `${productivityPct}%` : translate(language, 'no_action'));
</script>

<tr class:offline={!plc.is_online}>
  <td class="unit">{unitLabel}</td>
  <td class="status"><span class="dot" style={dotStyle}></span>{label}</td>
  <td class="time">{timeText}</td>
  <td class="recipe">{plc.recipe ?? ''}</td>
  <td class="productivity">{productivityText}</td>
</tr>

<style>
  tr {
    border-bottom: 1px solid var(--border-color);
  }

  tr:last-child {
    border-bottom: none;
  }

  tr.offline {
    opacity: 0.6;
  }

  td {
    padding: clamp(0.5rem, 1vh, 0.85rem) clamp(0.75rem, 1.2vw, 1.25rem);
    font-size: var(--font-tile-state);
    color: var(--text-primary);
  }

  .unit {
    font-weight: 700;
    white-space: nowrap;
  }

  .status {
    white-space: nowrap;
  }

  .dot {
    display: inline-block;
    width: 0.7em;
    height: 0.7em;
    border-radius: 50%;
    margin-right: 0.5em;
  }

  .time,
  .productivity {
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }

  .recipe {
    color: var(--text-secondary);
  }
</style>
