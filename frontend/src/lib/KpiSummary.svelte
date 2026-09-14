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

<table class="kpi-summary">
  <thead>
    <tr>
      <th>{translate($lang, 'kpi_busy')}</th>
      <th>{translate($lang, 'kpi_waiting')}</th>
      <th>{translate($lang, 'kpi_error')}</th>
      <th>{translate($lang, 'kpi_productivity')}</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>{busy}</td>
      <td>{waiting}</td>
      <td>{errorTime}</td>
      <td>{productivity}</td>
    </tr>
  </tbody>
</table>

<style>
  /* A genuine 4-column table: one header row (Busy | Waiting | Error |
     Productivity) above one value row — not the previous 2x2 grid of
     label/value pairs. table-layout: auto (the default) lets each column
     size to its own widest cell, so a long header like "Produktivität"
     (DE) simply widens its own column rather than wrapping or pushing
     into its neighbour; every other column stays only as wide as it
     needs to be. Centering both the header and its value in the same
     column keeps them visually paired without needing left/right
     alignment tricks. */
  .kpi-summary {
    flex: 0 0 auto;
    border-collapse: collapse;
    font-size: var(--font-kpi-summary);
  }

  .kpi-summary th,
  .kpi-summary td {
    padding: clamp(0.2rem, 0.5vh, 0.4rem) clamp(0.5rem, 1.1vw, 1rem);
    white-space: nowrap;
    text-align: center;
    border-right: 1px solid var(--border-color);
  }

  .kpi-summary th:last-child,
  .kpi-summary td:last-child {
    border-right: none;
  }

  .kpi-summary th {
    font-weight: 600;
    font-style: normal;
    color: var(--text-secondary);
    border-bottom: 1px solid var(--border-color);
  }

  .kpi-summary td {
    font-weight: 700;
    color: var(--text-primary);
    font-variant-numeric: tabular-nums;
  }
</style>
