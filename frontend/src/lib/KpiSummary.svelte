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
  <div class="kpi-row">
    <span class="kpi-item"><span class="kpi-label">{translate($lang, 'kpi_busy')}</span> {busy}</span>
    <span class="kpi-item"><span class="kpi-label">{translate($lang, 'kpi_waiting')}</span> {waiting}</span>
  </div>
  <div class="kpi-row">
    <span class="kpi-item"><span class="kpi-label">{translate($lang, 'kpi_error')}</span> {errorTime}</span>
    <span class="kpi-item"><span class="kpi-label">{translate($lang, 'kpi_productivity')}</span> {productivity}</span>
  </div>
</div>

<style>
  .kpi-summary {
    flex: 0 0 auto;
    display: flex;
    flex-direction: column;
    gap: clamp(0.1rem, 0.3vh, 0.25rem);
    font-size: var(--font-kpi-summary);
    color: var(--text-secondary);
    line-height: 1.3;
    white-space: nowrap;
  }

  .kpi-row {
    display: flex;
    gap: clamp(0.6rem, 1.2vw, 1.25rem);
  }

  .kpi-label {
    font-weight: 600;
  }
</style>
