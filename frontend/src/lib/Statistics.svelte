<script>
  import { onMount } from 'svelte';
  import { lang, auth } from './stores.js';
  import { translate } from './translations.js';
  import { formatUnitLabel } from './format.js';
  import { getAvailableDates, getDailySummary, ServiceApiError } from './serviceApi.js';

  function todayLocal() {
    const d = new Date();
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    return `${d.getFullYear()}-${mm}-${dd}`;
  }

  function formatHM(seconds) {
    const total = Math.max(0, Math.round(seconds ?? 0));
    const h = Math.floor(total / 3600);
    const m = Math.round((total % 3600) / 60);
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
  }

  let selectedDate = $state(todayLocal());
  let availableDates = $state([]);
  let machines = $state([]);
  let loadError = $state('');

  onMount(async () => {
    try {
      const data = await getAvailableDates();
      availableDates = data.dates;
    } catch {
      // Non-fatal — the date input still works without min/max bounds.
    }
  });

  // Historical data only (see task note: no live WS updates here) — fetch
  // once on mount and again whenever the picked date changes.
  $effect(() => {
    const date = selectedDate;
    loadError = '';
    getDailySummary(date)
      .then((data) => {
        if (date === selectedDate) machines = data.machines;
      })
      .catch((err) => {
        if (date !== selectedDate) return;
        machines = [];
        loadError = err instanceof ServiceApiError ? err.message : String(err);
      });
  });

  let minDate = $derived(availableDates[0]);
  let maxDate = $derived(todayLocal());

  // Group rows by group_name, preserving the backend's sorted order —
  // same grouping convention as MachineGroupSection.svelte on the Dashboard.
  let groupedRows = $derived.by(() => {
    const groups = [];
    let current = null;
    for (const m of machines) {
      if (!current || current.name !== m.group_name) {
        current = { name: m.group_name, rows: [] };
        groups.push(current);
      }
      current.rows.push(m);
    }
    return groups;
  });

  let csvUrl = $derived(
    `/api/stats/daily-summary/csv?date=${encodeURIComponent(selectedDate)}&token=${encodeURIComponent($auth.token ?? '')}`,
  );
</script>

<div class="statistics">
  <div class="toolbar">
    <label class="date-field">
      <span>{translate($lang, 'stats_date_label')}</span>
      <input type="date" bind:value={selectedDate} min={minDate} max={maxDate} />
    </label>
    <a class="csv-button" href={csvUrl}>{translate($lang, 'stats_download_csv')}</a>
  </div>

  {#if loadError}
    <p class="error">{loadError}</p>
  {:else if machines.length === 0}
    <div class="empty-state">{translate($lang, 'stats_no_data')}</div>
  {:else}
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>{translate($lang, 'stats_col_unit')}</th>
            <th>{translate($lang, 'stats_col_ip')}</th>
            <th>{translate($lang, 'stats_col_baking')}</th>
            <th>{translate($lang, 'stats_col_ready')}</th>
            <th>{translate($lang, 'stats_col_heating')}</th>
            <th>{translate($lang, 'stats_col_error')}</th>
            <th>{translate($lang, 'stats_col_cold')}</th>
            <th>{translate($lang, 'stats_col_offline')}</th>
            <th>{translate($lang, 'stats_col_productivity')}</th>
          </tr>
        </thead>
        <tbody>
          {#each groupedRows as group (group.name)}
            <tr class="group-row"><td colspan="9">{group.name}</td></tr>
            {#each group.rows as m (m.plc_ip)}
              <tr>
                <td>{formatUnitLabel(m.unit_number, $lang)}</td>
                <td class="mono">{m.plc_ip}</td>
                <td>{formatHM(m.baking_seconds)}</td>
                <td>{formatHM(m.ready_seconds)}</td>
                <td>{formatHM(m.heating_seconds)}</td>
                <td>{formatHM(m.error_seconds)}</td>
                <td>{formatHM(m.cold_seconds)}</td>
                <td>{formatHM(m.offline_seconds)}</td>
                <td>{m.productivity_pct.toFixed(1)}%</td>
              </tr>
            {/each}
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>

<style>
  .statistics {
    height: 100%;
    overflow-y: auto;
    padding: clamp(1rem, 2vh, 2rem) clamp(1rem, 2vw, 2rem);
  }

  .toolbar {
    display: flex;
    align-items: flex-end;
    flex-wrap: wrap;
    gap: clamp(0.75rem, 1.5vw, 1.5rem);
    margin-bottom: clamp(1rem, 2vh, 1.75rem);
  }

  .date-field {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    font-size: var(--font-toggle);
    color: var(--text-secondary);
  }

  .date-field input {
    font-size: var(--font-toggle);
    padding: clamp(0.4rem, 0.8vh, 0.6rem);
    border-radius: var(--radius);
    border: 1px solid var(--border-color);
    background: var(--bg-app);
    color: var(--text-primary);
  }

  .csv-button {
    font-size: var(--font-toggle);
    font-weight: 600;
    padding: clamp(0.5rem, 1vh, 0.75rem) clamp(1rem, 1.6vw, 1.5rem);
    border-radius: var(--radius);
    background: var(--opelka-blue);
    color: var(--opelka-blue-fg);
    text-decoration: none;
    white-space: nowrap;
  }

  .empty-state {
    color: var(--text-secondary);
    font-size: var(--font-group-header);
    padding: clamp(2rem, 6vh, 4rem) 0;
    text-align: center;
  }

  .error {
    color: var(--danger-bg);
    font-size: var(--font-toggle);
    font-weight: 600;
  }

  .table-wrap {
    overflow-x: auto;
  }

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--font-toggle);
  }

  th,
  td {
    text-align: left;
    padding: clamp(0.4rem, 0.8vh, 0.65rem) clamp(0.6rem, 1vw, 1rem);
    border-bottom: 1px solid var(--border-color);
    white-space: nowrap;
  }

  th {
    color: var(--text-secondary);
    font-weight: 600;
  }

  td.mono {
    font-family: ui-monospace, Consolas, monospace;
    color: var(--text-secondary);
  }

  .group-row td {
    font-size: var(--font-group-header);
    font-weight: 700;
    color: var(--text-primary);
    border-bottom: none;
    padding-top: clamp(1rem, 2vh, 1.5rem);
  }

  tbody tr:first-child.group-row td {
    padding-top: 0;
  }
</style>
