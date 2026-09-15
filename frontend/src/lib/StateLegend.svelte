<script>
  // Colour key for the six MachineTile state colours (see FryerTile.svelte /
  // app.css's --state-* tokens) — purely explanatory, reuses the existing
  // translated state labels rather than hardcoding English.
  import { translate } from './translations.js';

  let { language = 'en' } = $props();

  const ITEMS = [
    { key: 'ready', labelKey: 'state_ready' },
    { key: 'baking', labelKey: 'state_baking' },
    { key: 'heating', labelKey: 'state_heating' },
    { key: 'cold', labelKey: 'state_cold' },
    { key: 'error', labelKey: 'state_error' },
    { key: 'near-completion', labelKey: 'state_near_completion' },
  ];
</script>

<div class="legend">
  {#each ITEMS as item (item.key)}
    <div class="legend-item">
      <span class="dot dot-{item.key}"></span>
      <span class="label">{translate(language, item.labelKey)}</span>
    </div>
  {/each}
</div>

<style>
  /* Sits inline in Dashboard.svelte's .toolbar row, grouped together with
     the Block/List view toggle on the right side of that row (legend
     first, then the toggle right after it — see .toolbar's own
     justify-content: flex-end). flex: 0 1 auto (not 1 1 auto) so this
     only takes the width its own content needs and doesn't stretch to
     fill the row now that it's no longer meant to span the full width;
     flex-wrap still lets all six dots wrap to a second line internally
     as a unit, rather than fighting the toggle button for space at high
     --ui-scale/narrow viewports (.toolbar's own wrap handles the case
     where even that doesn't fit next to the toggle). */
  .legend {
    flex: 0 1 auto;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: flex-end;
    column-gap: 1.25rem;
    row-gap: 0.3rem;
  }

  .legend-item {
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }

  .dot {
    width: 0.65rem;
    height: 0.65rem;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .label {
    font-size: 0.75rem;
    color: var(--text-secondary);
    white-space: nowrap;
  }

  .dot-ready {
    background: var(--state-ready);
  }

  .dot-baking {
    background: var(--state-baking);
  }

  .dot-heating {
    background: var(--state-heating);
  }

  .dot-cold {
    background: var(--state-cold);
  }

  .dot-error {
    background: var(--state-error);
  }

  .dot-near-completion {
    background: var(--state-near-completion);
  }
</style>
