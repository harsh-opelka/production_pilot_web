<script>
  import { lang } from './stores.js';
  import { translate } from './translations.js';
  import { formatHoursMinutes } from './format.js';

  const REFRESH_MS = 60_000;

  let totals = $state(null);

  async function load() {
    try {
      const res = await fetch('/api/stats/today-totals');
      if (!res.ok) return;
      totals = await res.json();
    } catch {
      // Non-fatal — this is a secondary glance, not core dashboard data.
      // Keep whatever was last shown rather than blanking it on a blip.
    }
  }

  $effect(() => {
    load();
    const interval = setInterval(load, REFRESH_MS);
    return () => clearInterval(interval);
  });

  let hasData = $derived(totals?.has_data === true);
  let busy = $derived(hasData ? formatHoursMinutes(totals.baking_seconds, $lang) : translate($lang, 'kpi_no_data'));
  let waiting = $derived(hasData ? formatHoursMinutes(totals.waiting_seconds, $lang) : translate($lang, 'kpi_no_data'));
  let errorTime = $derived(hasData ? formatHoursMinutes(totals.error_seconds, $lang) : translate($lang, 'kpi_no_data'));
  let productivity = $derived(hasData ? `${totals.productivity_pct}%` : translate($lang, 'kpi_no_data'));
</script>

<div class="kpi-summary">
  <div class="kpi-cell">
    <span class="kpi-label">{translate($lang, 'kpi_busy')}</span>
    <span class="kpi-value">{busy}</span>
  </div>
  <div class="kpi-cell">
    <span class="kpi-label">{translate($lang, 'kpi_waiting')}</span>
    <span class="kpi-value">{waiting}</span>
  </div>
  <div class="kpi-cell">
    <span class="kpi-label">{translate($lang, 'kpi_error')}</span>
    <span class="kpi-value">{errorTime}</span>
  </div>
  <div class="kpi-cell">
    <span class="kpi-label">{translate($lang, 'kpi_productivity')}</span>
    <span class="kpi-value">{productivity}</span>
  </div>
</div>

<style>
  /* 2x2 grid, filled left-to-right/top-to-bottom by DOM order: Busy |
     Waiting on row 1, Error | Productivity on row 2. Both columns share
     one width (auto-sized to the widest label/value) so the two rows'
     values line up in a clean column instead of drifting per-row. */
  .kpi-summary {
    flex: 0 0 auto;
    display: grid;
    grid-template-columns: repeat(2, auto);
    column-gap: clamp(0.9rem, 1.6vw, 1.75rem);
    row-gap: clamp(0.15rem, 0.35vh, 0.3rem);
    font-size: var(--font-kpi-summary);
  }

  .kpi-cell {
    display: flex;
    align-items: baseline;
    gap: 0.4em;
    white-space: nowrap;
  }

  .kpi-label {
    font-weight: 600;
    color: var(--text-secondary);
  }

  .kpi-value {
    font-weight: 700;
    color: var(--text-primary);
    font-variant-numeric: tabular-nums;
  }
</style>
