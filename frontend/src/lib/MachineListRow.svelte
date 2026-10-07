<script>
  import { formatDuration, formatRecipe, formatTemperature, formatUnitNumber, stateLabel } from './format.js';
  import { translate } from './translations.js';
  import { nowTick } from './stores.js';

  let { plc, language = 'en', productivityPct = null } = $props();

  // Same "Fast fertig"/"Almost finished" colour override as FryerTile.svelte.
  let stateKey = $derived(plc.near_completion ? 'near-completion' : plc.state.toLowerCase());
  let label = $derived(stateLabel(plc, language));
  let unitLabel = $derived(formatUnitNumber(plc.unit_number));
  let dotStyle = $derived(plc.is_online ? `background: var(--state-${stateKey});` : `background: var(--offline-border);`);
  let isBlocked = $derived(plc.is_online && plc.state === 'BLOCKED');
  let isLightBorder = $derived(plc.is_online && (plc.state === 'STANDBY' || plc.state === 'UNRECOGNIZED'));
  let showRemaining = $derived(plc.is_online && plc.state === 'BAKING' && plc.remaining_seconds != null);

  const TIMER_STATES = new Set(['COLD', 'HEATING', 'HOT', 'STANDBY', 'WAITING', 'BLOCKED', 'ERROR', 'UNRECOGNIZED']);
  let showElapsed = $derived(!showRemaining && plc.is_online && TIMER_STATES.has(plc.state) && plc.state_entered_at != null);

  let timeText = $derived(
    showRemaining
      ? formatDuration(plc.remaining_seconds, language)
      : showElapsed
        ? formatDuration(($nowTick - Date.parse(plc.state_entered_at)) / 1000, language)
        : translate(language, 'no_action'),
  );
  // Blank ("—") rather than stale values while offline — same as FryerTile.
  let recipeText = $derived(formatRecipe(plc.is_online ? plc.recipe_name : null));
  let temperatureText = $derived(
    plc.is_online ? formatTemperature(plc.oil_temp_current, plc.oil_temp_target) : formatTemperature(null, null),
  );
  let productivityText = $derived(productivityPct != null ? `${productivityPct}%` : translate(language, 'no_action'));
</script>

<tr class:offline={!plc.is_online}>
  <td class="unit">{unitLabel}</td>
  <td class="status"><span class="dot" class:blocked={isBlocked} class:light-border={isLightBorder} style={dotStyle}></span>{label}</td>
  <td class="time">{timeText}</td>
  <td class="recipe">{recipeText}</td>
  <td class="temperature">{temperatureText}</td>
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

  /* Standby (no temperature) / Unknown: same lighter ring as their tile. */
  .dot.light-border {
    outline: 2px solid var(--state-standby-border);
    outline-offset: 1px;
  }

  .dot.blocked {
    outline: 2px dashed var(--state-blocked-border);
    outline-offset: 1px;
  }

  .time,
  .temperature,
  .productivity {
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }

  .recipe {
    color: var(--text-secondary);
  }
</style>
