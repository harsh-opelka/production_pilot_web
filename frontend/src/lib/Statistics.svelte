<script>
  import { onMount } from 'svelte';
  import { lang, auth, theme, nowTick } from './stores.js';
  import { translate } from './translations.js';
  import { formatUnitLabel, todayLocalDate } from './format.js';
  import {
    getAvailableDates,
    getDailySummary,
    getRangeSummary,
    getRecordingStatus,
    ServiceApiError,
  } from './serviceApi.js';
  import SnapshotChart from './SnapshotChart.svelte';
  import TrendLineChart from './TrendLineChart.svelte';

  function daysAgoLocal(n) {
    const d = new Date();
    d.setDate(d.getDate() - n);
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

  let selectedDate = $state(todayLocalDate());
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
  let maxDate = $derived(todayLocalDate());

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

  // --- Snapshot / Trend / Live toggle -----------------------------------
  // 'selectedDate' above is untouched by this toggle, so flipping between
  // views never loses it — Snapshot reuses it directly (no separate date
  // input of its own), and it keeps driving the table/CSV regardless of
  // which chart view is showing.
  let viewMode = $state('snapshot'); // 'snapshot' | 'trend' | 'live'

  // --- Live mode ---------------------------------------------------------
  const LIVE_REFRESH_MS = 30_000;

  let liveMachines = $state([]);
  let liveError = $state('');
  let liveLastUpdated = $state(null); // epoch ms of the last successful fetch
  let liveRecordingEnabled = $state(null); // null = unknown, true/false once checked

  async function loadLive() {
    try {
      const summary = await getDailySummary(todayLocalDate());
      liveMachines = summary.machines;
      liveLastUpdated = Date.now();
      liveError = '';
    } catch (err) {
      liveError = err instanceof ServiceApiError ? err.message : String(err);
    }
    try {
      // Service-level-only endpoint — a Management session simply can't
      // see it, so the "recording off" banner below just stays hidden
      // rather than turning this into a hard error.
      const status = await getRecordingStatus();
      liveRecordingEnabled = status.enabled;
    } catch {
      liveRecordingEnabled = null;
    }
  }

  $effect(() => {
    if (viewMode !== 'live') return;
    loadLive();
    const interval = setInterval(loadLive, LIVE_REFRESH_MS);
    return () => clearInterval(interval);
  });

  let liveSecondsAgo = $derived(
    liveLastUpdated != null ? Math.max(0, Math.round(($nowTick - liveLastUpdated) / 1000)) : null,
  );

  let rangeStart = $state(daysAgoLocal(6)); // last 7 days including today, by default
  let rangeEnd = $state(todayLocalDate());
  let rangeDays = $state([]); // [{ date, machines }]
  let rangeError = $state('');

  // Only fetches once Trend is actually selected — no point hitting the
  // range endpoint while the user is looking at Snapshot.
  $effect(() => {
    if (viewMode !== 'trend') return;
    const start = rangeStart;
    const end = rangeEnd;
    rangeError = '';
    getRangeSummary(start, end)
      .then((data) => {
        if (start === rangeStart && end === rangeEnd) rangeDays = data.days;
      })
      .catch((err) => {
        if (start !== rangeStart || end !== rangeEnd) return;
        rangeDays = [];
        rangeError = err instanceof ServiceApiError ? err.message : String(err);
      });
  });

  // Machines can differ day to day (a PLC only appears in a day's list if
  // it actually logged a transition that day), so the set of lines to
  // plot is the UNION across the whole range, keyed by plc_ip — using
  // each machine's most recent appearance for its label.
  let machineIndex = $derived.by(() => {
    const index = new Map();
    for (const day of rangeDays) {
      for (const m of day.machines) {
        index.set(m.plc_ip, { group_name: m.group_name, unit_number: m.unit_number });
      }
    }
    return index;
  });

  function buildSeries(metricKey, language) {
    return [...machineIndex.entries()].map(([ip, info]) => ({
      ip,
      label: `${info.group_name} — ${formatUnitLabel(info.unit_number, language)}`,
      points: rangeDays.map((day) => {
        const m = day.machines.find((x) => x.plc_ip === ip);
        // A day this machine has no rows for is a genuine gap (we have NO
        // data), not a 0 (which would claim "measured, and it was zero")
        // — null lets the chart draw an honest break instead of a fake
        // flat line through days nothing was recorded (see
        // TrendLineChart's spanGaps: false).
        if (!m) return { date: day.date, value: null };
        const raw = m[metricKey];
        return { date: day.date, value: metricKey === 'productivity_pct' ? raw : raw / 60 };
      }),
    }));
  }

  let bakingSeries = $derived(buildSeries('baking_seconds', $lang));
  let waitingSeries = $derived(buildSeries('ready_seconds', $lang));
  let errorSeries = $derived(buildSeries('error_seconds', $lang));
  let productivitySeries = $derived(buildSeries('productivity_pct', $lang));
</script>

<div class="statistics">
  <div class="toolbar">
    {#if viewMode !== 'live'}
      <label class="date-field">
        <span>{translate($lang, 'stats_date_label')}</span>
        <input type="date" bind:value={selectedDate} min={minDate} max={maxDate} />
      </label>
    {/if}
    <a class="csv-button" href={csvUrl}>{translate($lang, 'stats_download_csv')}</a>

    <div class="view-toggle" role="group" aria-label="Chart view">
      <button class:active={viewMode === 'snapshot'} onclick={() => (viewMode = 'snapshot')}>
        {translate($lang, 'stats_view_snapshot')}
      </button>
      <button class:active={viewMode === 'trend'} onclick={() => (viewMode = 'trend')}>
        {translate($lang, 'stats_view_trend')}
      </button>
      <button class:active={viewMode === 'live'} onclick={() => (viewMode = 'live')}>
        {translate($lang, 'stats_view_live')}
      </button>
    </div>
  </div>

  {#if viewMode === 'trend'}
    <div class="range-toolbar">
      <label class="date-field">
        <span>{translate($lang, 'stats_range_start')}</span>
        <input type="date" bind:value={rangeStart} max={rangeEnd} />
      </label>
      <label class="date-field">
        <span>{translate($lang, 'stats_range_end')}</span>
        <input type="date" bind:value={rangeEnd} min={rangeStart} max={todayLocalDate()} />
      </label>
    </div>
  {/if}

  <div class="charts-section">
    {#if viewMode === 'snapshot'}
      <SnapshotChart {machines} lang={$lang} theme={$theme} />
    {:else if viewMode === 'live'}
      {#if liveRecordingEnabled === false}
        <p class="recording-off-note">{translate($lang, 'stats_live_recording_off')}</p>
      {:else if liveError}
        <p class="error">{liveError}</p>
      {:else}
        <SnapshotChart machines={liveMachines} lang={$lang} theme={$theme} />
        {#if liveSecondsAgo != null}
          <p class="live-updated">{translate($lang, 'stats_live_last_updated', { seconds: liveSecondsAgo })}</p>
        {/if}
      {/if}
    {:else if rangeError}
      <p class="error">{rangeError}</p>
    {:else}
      <div class="trend-grid">
        <TrendLineChart title={translate($lang, 'stats_metric_baking')} series={bakingSeries} theme={$theme} />
        <TrendLineChart title={translate($lang, 'stats_metric_waiting')} series={waitingSeries} theme={$theme} />
        <TrendLineChart title={translate($lang, 'stats_metric_error')} series={errorSeries} theme={$theme} />
        <TrendLineChart
          title={translate($lang, 'stats_metric_productivity')}
          series={productivitySeries}
          isPercent
          theme={$theme}
        />
      </div>
    {/if}
  </div>

  <p class="output-note">{translate($lang, 'stats_output_note')}</p>

  <!-- Headers always render, regardless of viewMode/loadError/empty data —
       only the tbody content varies. A missing/empty date shouldn't take
       the table structure away with it; the "no data" message belongs
       inside the table, not in place of it. -->
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>{translate($lang, 'stats_col_unit')}</th>
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
        {#if loadError}
          <tr><td colspan="8" class="table-message error">{loadError}</td></tr>
        {:else if machines.length === 0}
          <tr><td colspan="8" class="table-message">{translate($lang, 'stats_no_data')}</td></tr>
        {:else}
          {#each groupedRows as group (group.name)}
            <tr class="group-row"><td colspan="8">{group.name}</td></tr>
            {#each group.rows as m (m.plc_ip)}
              <tr>
                <td>{formatUnitLabel(m.unit_number, $lang)}</td>
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
        {/if}
      </tbody>
    </table>
  </div>
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

  .view-toggle {
    display: flex;
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    overflow: hidden;
    margin-left: auto;
  }

  .view-toggle button {
    font-size: var(--font-view-toggle);
    padding: clamp(0.4rem, 0.7vh, 0.7rem) clamp(0.9rem, 1.4vw, 1.5rem);
    border: none;
    background: var(--bg-panel);
    color: var(--text-secondary);
    transition: background 0.15s, color 0.15s;
  }

  .view-toggle button.active {
    background: var(--opelka-blue);
    color: var(--opelka-blue-fg);
    font-weight: 600;
  }

  .range-toolbar {
    display: flex;
    flex-wrap: wrap;
    gap: clamp(0.75rem, 1.5vw, 1.5rem);
    margin-bottom: clamp(1rem, 2vh, 1.5rem);
  }

  .charts-section {
    margin-bottom: clamp(0.75rem, 1.5vh, 1.25rem);
  }

  .trend-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 22rem), 1fr));
    gap: clamp(0.75rem, 1.5vw, 1.5rem);
  }

  .recording-off-note {
    margin: 0;
    padding: clamp(1.25rem, 3vh, 2rem);
    background: var(--bg-panel);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    color: var(--text-secondary);
    font-size: var(--font-toggle);
    text-align: center;
  }

  .live-updated {
    margin: clamp(0.4rem, 0.8vh, 0.6rem) 0 0;
    color: var(--text-secondary);
    font-size: var(--font-tile-sub);
    text-align: right;
  }

  .output-note {
    margin: 0 0 clamp(1.25rem, 2.5vh, 2rem);
    color: var(--text-secondary);
    font-size: 0.85em;
    font-style: italic;
  }

  .table-message {
    color: var(--text-secondary);
    font-size: var(--font-group-header);
    padding: clamp(2rem, 6vh, 4rem) 0;
    text-align: center;
    white-space: normal;
    border-bottom: none;
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
