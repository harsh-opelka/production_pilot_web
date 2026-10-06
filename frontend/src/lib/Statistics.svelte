<script>
  import { onMount } from 'svelte';
  import { lang, auth, theme, nowTick, statsHiddenColumns } from './stores.js';
  import { translate } from './translations.js';
  import { formatHoursMinutes, formatUnitLabel, formatUnitNumber, todayLocalDate } from './format.js';
  import {
    getAvailableDates,
    getDailySummary,
    getRangeSummary,
    getRecordingStatus,
    getProductivityTarget,
    ServiceApiError,
  } from './serviceApi.js';
  import SnapshotChart from './SnapshotChart.svelte';
  import TrendLineChart from './TrendLineChart.svelte';
  import KpiRow from './KpiRow.svelte';
  import ParetoChart from './ParetoChart.svelte';
  import TimelineView from './TimelineView.svelte';
  import Sparkline from './Sparkline.svelte';

  function daysAgoLocal(n) {
    const d = new Date();
    d.setDate(d.getDate() - n);
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    return `${d.getFullYear()}-${mm}-${dd}`;
  }

  // Every observed-time bucket from stats._SECONDS_KEYS — the productivity
  // denominator (Hot and Blocked count as available time for now, same as
  // the backend's shared stats.productivity_pct).
  const TRACKED_KEYS = [
    'baking_seconds',
    'waiting_seconds',
    'heating_seconds',
    'hot_seconds',
    'blocked_seconds',
    'error_seconds',
    'cold_seconds',
    'offline_seconds',
  ];

  let selectedDate = $state(todayLocalDate());
  let availableDates = $state([]);
  let machines = $state([]);
  let totals = $state(null);
  let comparison = $state(null);
  let productivityTarget = $state(null);
  let loadError = $state('');

  onMount(async () => {
    try {
      const data = await getAvailableDates();
      availableDates = data.dates;
    } catch {
      // Non-fatal — the date input still works without min/max bounds.
    }
  });

  onMount(async () => {
    try {
      const data = await getProductivityTarget();
      productivityTarget = data.target_pct;
    } catch {
      // Non-fatal — the productivity KPI card just won't show a
      // below/at-target colour without it.
    }
  });

  // --- Overview / Trend / Timeline toggle -----------------------------------
  // 'selectedDate' above is untouched by this toggle, so flipping between
  // views never loses it — Overview and Timeline both reuse it directly
  // (no separate date input of their own), and it keeps driving the
  // KPI row / Pareto chart / table regardless of which view is showing.
  let viewMode = $state('overview'); // 'overview' | 'trend' | 'timeline'

  // --- Daily summary (KPI row, Pareto chart, table, Overview chart) --------
  // Driven entirely by `selectedDate` (KPI cards always compare against
  // the 7-day average — see stats.compute_seven_day_average). Today
  // auto-refreshes every 15s; any past date fetches once with no
  // auto-refresh. The caption under the toolbar shows how long ago the
  // numbers were fetched and (today only) a countdown to the next refresh.
  const LIVE_REFRESH_MS = 15_000;

  let lastUpdated = $state(null); // Date of the last successful daily-summary fetch; null until loaded
  let nextRefreshAt = $state(null); // epoch ms of the next scheduled refresh; null for past dates
  let recordingEnabled = $state(null); // null = unknown/not-today, true/false once checked for today

  $effect(() => {
    const date = selectedDate;
    const isToday = date === todayLocalDate();
    loadError = '';
    lastUpdated = null;
    nextRefreshAt = null;
    recordingEnabled = null;

    async function load() {
      try {
        const summary = await getDailySummary(date, 'avg_7d');
        if (date !== selectedDate) return;
        machines = summary.machines;
        totals = summary.totals;
        comparison = summary.comparison ?? null;
        loadError = '';
        lastUpdated = new Date();
      } catch (err) {
        if (date !== selectedDate) return;
        machines = [];
        totals = null;
        comparison = null;
        loadError = err instanceof ServiceApiError ? err.message : String(err);
      }

      if (!isToday) return;
      try {
        // Service-level-only endpoint — a Management session simply can't
        // see it, so the "recording off" banner below just stays hidden
        // rather than turning this into a hard error.
        const status = await getRecordingStatus();
        if (date === selectedDate) recordingEnabled = status.enabled;
      } catch {
        if (date === selectedDate) recordingEnabled = null;
      }
    }

    load();
    if (!isToday) return; // past date: fetch once, no auto-refresh
    nextRefreshAt = Date.now() + LIVE_REFRESH_MS;
    const interval = setInterval(() => {
      nextRefreshAt = Date.now() + LIVE_REFRESH_MS;
      load();
    }, LIVE_REFRESH_MS);
    return () => clearInterval(interval);
  });

  // Ticks every second off the shared nowTick store.
  let refreshCaption = $derived.by(() => {
    if (!lastUpdated) return '';
    const ago = Math.max(0, Math.round(($nowTick - lastUpdated.getTime()) / 1000));
    const agoText =
      ago < 60
        ? translate($lang, 'stats_updated_seconds_ago', { n: ago })
        : translate($lang, 'stats_updated_minutes_ago', { n: Math.floor(ago / 60) });
    if (nextRefreshAt == null) return agoText;
    const inSeconds = Math.max(0, Math.ceil((nextRefreshAt - $nowTick) / 1000));
    return `${agoText} · ${translate($lang, 'stats_refreshing_in', { n: inSeconds })}`;
  });

  let minDate = $derived(availableDates[0]);
  let maxDate = $derived(todayLocalDate());

  // --- Table sorting ---------------------------------------------------------
  // Sorting is per-column, ascending/descending toggled by re-clicking the
  // same header — applied WITHIN each group's rows only, never across
  // groups (the group-header structure stays intact, see groupedRows).
  // Default: Machine 1, 2, 3, ... within each group. Ties on any other
  // column also fall back to unit order, so the table never shows
  // machines in whatever order the backend happened to return them.
  let sortColumn = $state('unit_number');
  let sortDirection = $state('asc'); // 'asc' | 'desc'

  function toggleSort(column) {
    if (sortColumn === column) {
      sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
    } else {
      sortColumn = column;
      sortDirection = 'asc';
    }
  }

  function sortArrow(column) {
    if (sortColumn !== column) return '';
    return sortDirection === 'asc' ? ' ▲' : ' ▼';
  }

  // Group rows by group_name, preserving the backend's sorted order —
  // same grouping convention as MachineGroupSection.svelte on the
  // Dashboard — then sort each group's own rows by the active column.
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
    const col = sortColumn;
    const dir = sortDirection === 'asc' ? 1 : -1;
    for (const group of groups) {
      group.rows.sort((a, b) => {
        const primary =
          typeof a[col] === 'string' ? a[col].localeCompare(b[col], undefined, { numeric: true }) : a[col] - b[col];
        return primary * dir || a.unit_number - b.unit_number;
      });
    }
    return groups;
  });

  // Worst/best-performer highlighting — computed across ALL machines (not
  // per group; see task note), restricted to machines that actually have
  // any recorded time this day (a configured-but-unused machine reads
  // 0.0% by default, which isn't a meaningful "worst performer"), and only
  // when there's more than one such machine AND their values actually
  // differ — flagging every row the same colour when all are tied would
  // be noise, not signal.
  let machinesWithData = $derived(
    machines.filter(
      (m) =>
        TRACKED_KEYS.reduce((sum, k) => sum + m[k], 0) > 0,
    ),
  );

  let worstPlcIp = $derived.by(() => {
    if (machinesWithData.length < 2) return null;
    const values = machinesWithData.map((m) => m.productivity_pct);
    const min = Math.min(...values);
    if (min === Math.max(...values)) return null;
    return machinesWithData.find((m) => m.productivity_pct === min).plc_ip;
  });

  let bestPlcIp = $derived.by(() => {
    if (machinesWithData.length < 2) return null;
    const values = machinesWithData.map((m) => m.productivity_pct);
    const max = Math.max(...values);
    if (max === Math.min(...values)) return null;
    return machinesWithData.find((m) => m.productivity_pct === max).plc_ip;
  });

  // Server-side exports (see server.py /api/stats/daily-summary/{csv,xlsx,pdf}),
  // reached via plain <a href> downloads — hence the token query param.
  const EXPORT_FORMATS = [
    { format: 'xlsx', labelKey: 'stats_export_xlsx' },
    { format: 'csv', labelKey: 'stats_export_csv' },
    { format: 'pdf', labelKey: 'stats_export_pdf' },
  ];
  function exportUrl(format) {
    return `/api/stats/daily-summary/${format}?date=${encodeURIComponent(selectedDate)}&token=${encodeURIComponent($auth.token ?? '')}`;
  }

  // Which dropdown is open: 'export' | 'columns' | null. Closed by any
  // click outside it (or its trigger button), or Escape.
  let openMenu = $state(null);
  function toggleMenu(name) {
    openMenu = openMenu === name ? null : name;
  }

  // The column picker's icon lives in the table's own header row
  // (Odoo-style), but the popover itself is rendered OUTSIDE .table-wrap:
  // that element scrolls horizontally (overflow-x: auto), so anything
  // absolutely positioned inside it grows its scroll area instead of
  // floating over the page. The popover is absolutely positioned within
  // .table-area instead, anchored under the icon at the moment it opens —
  // it takes no layout space, so opening/closing never resizes anything.
  let tableAreaEl;
  let columnMenuPos = $state({ top: 0, right: 0 });
  function toggleColumnMenu(event) {
    const icon = event.currentTarget.getBoundingClientRect();
    const area = tableAreaEl.getBoundingClientRect();
    columnMenuPos = { top: icon.bottom - area.top + 4, right: area.right - icon.right };
    toggleMenu('columns');
  }
  // The anchor would drift if the table scrolls sideways or the window
  // resizes, so just close it then.
  function closeColumnMenu() {
    if (openMenu === 'columns') openMenu = null;
  }
  function onWindowClick(event) {
    if (openMenu && !event.target.closest('.menu-wrap, .picker-button, .column-popover')) openMenu = null;
  }
  function onWindowKeydown(event) {
    if (event.key === 'Escape') openMenu = null;
  }

  let rangeStart = $state(daysAgoLocal(6)); // last 7 days including today, by default
  let rangeEnd = $state(todayLocalDate());
  let rangeDays = $state([]); // [{ date, machines }]
  let rangeError = $state('');

  // Only fetches once Trend is actually selected — no point hitting the
  // range endpoint while the user is looking at another view.
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
        // Raw seconds (or the raw percent for productivity) — TrendLineChart
        // itself picks the display unit from the largest value plotted
        // across all its series (see format.js's pickDurationUnit).
        return { date: day.date, value: m[metricKey] };
      }),
    }));
  }

  let bakingSeries = $derived(buildSeries('baking_seconds', $lang));
  let waitingSeries = $derived(buildSeries('waiting_seconds', $lang));
  let errorSeries = $derived(buildSeries('error_seconds', $lang));
  let productivitySeries = $derived(buildSeries('productivity_pct', $lang));

  // All-machines daily aggregates over the LAST 7 days of the selected
  // range, for the sparklines on the Productivity and Error panels. A day
  // with no recorded machines is null (a gap), not 0 — same rule as
  // buildSeries. Productivity is weighted (total baking over total
  // tracked time), matching stats.compute_totals, not a per-machine mean.
  let lastWeekDays = $derived(rangeDays.slice(-7));
  let productivitySpark = $derived(
    lastWeekDays.map((day) => {
      const tracked = day.machines.reduce((sum, m) => sum + TRACKED_KEYS.reduce((s, k) => s + m[k], 0), 0);
      const baking = day.machines.reduce((sum, m) => sum + m.baking_seconds, 0);
      return { date: day.date, value: day.machines.length && tracked > 0 ? (baking / tracked) * 100 : null };
    }),
  );
  let errorCountSpark = $derived(
    lastWeekDays.map((day) => ({
      date: day.date,
      value: day.machines.length ? day.machines.reduce((sum, m) => sum + m.error_count, 0) : null,
    })),
  );

  // kind drives cell formatting (see cellText). Every duration renders
  // as "1h 24m" — never a bare number — matching the exports.
  // serviceOnly: IPs are Service-level detail (same tier as the output
  // note above the table). locked: Unit always stays visible so rows
  // remain identifiable.
  const ALL_COLUMNS = [
    { key: 'unit_number', labelKey: 'stats_col_unit', kind: 'unit', locked: true },
    { key: 'plc_ip', labelKey: 'stats_col_ip', kind: 'text', serviceOnly: true },
    { key: 'baking_seconds', labelKey: 'stats_col_baking', kind: 'duration' },
    { key: 'waiting_seconds', labelKey: 'stats_col_waiting', kind: 'duration' },
    { key: 'heating_seconds', labelKey: 'stats_col_heating', kind: 'duration' },
    { key: 'hot_seconds', labelKey: 'stats_col_hot', kind: 'duration' },
    { key: 'blocked_seconds', labelKey: 'stats_col_blocked', kind: 'duration' },
    { key: 'error_seconds', labelKey: 'stats_col_error', kind: 'duration' },
    { key: 'error_count', labelKey: 'stats_col_error_count', kind: 'count' },
    { key: 'cold_seconds', labelKey: 'stats_col_cold', kind: 'duration' },
    { key: 'offline_seconds', labelKey: 'stats_col_offline', kind: 'duration' },
    // UNKNOWN/SERVER_STOPPED marker spans — server downtime, not machine time.
    { key: 'untracked_seconds', labelKey: 'stats_col_no_data', kind: 'duration' },
    { key: 'productivity_pct', labelKey: 'stats_col_productivity', kind: 'pct' },
  ];

  let availableColumns = $derived(ALL_COLUMNS.filter((c) => !c.serviceOnly || $auth.level === 'service'));
  let columns = $derived(availableColumns.filter((c) => c.locked || !$statsHiddenColumns.includes(c.key)));

  function toggleColumn(key) {
    statsHiddenColumns.update((hidden) => (hidden.includes(key) ? hidden.filter((k) => k !== key) : [...hidden, key]));
  }

  function cellText(col, m, language) {
    const v = m[col.key];
    switch (col.kind) {
      case 'unit':
        return formatUnitNumber(v); // bare "1", "2", ... like block/list view
      case 'duration':
        return formatHoursMinutes(v, language);
      case 'pct':
        return `${(v ?? 0).toFixed(1)}%`;
      default:
        return v ?? '';
    }
  }
</script>

<svelte:window onclick={onWindowClick} onkeydown={onWindowKeydown} onresize={closeColumnMenu} />

<div class="statistics">
  <div class="toolbar">
    <label class="date-field">
      <span>{translate($lang, 'stats_date_label')}</span>
      <input type="date" bind:value={selectedDate} min={minDate} max={maxDate} />
    </label>
    <div class="menu-wrap">
      <button
        type="button"
        class="export-button"
        aria-haspopup="menu"
        aria-expanded={openMenu === 'export'}
        onclick={() => toggleMenu('export')}
      >
        {translate($lang, 'stats_export')} ▾
      </button>
      {#if openMenu === 'export'}
        <div class="menu" role="menu">
          {#each EXPORT_FORMATS as item (item.format)}
            <a role="menuitem" href={exportUrl(item.format)} download onclick={() => (openMenu = null)}>
              {translate($lang, item.labelKey)}
            </a>
          {/each}
        </div>
      {/if}
    </div>

    <div class="view-toggle" role="group" aria-label="Chart view">
      <button class:active={viewMode === 'overview'} onclick={() => (viewMode = 'overview')}>
        {translate($lang, 'stats_view_overview')}
      </button>
      <button class:active={viewMode === 'trend'} onclick={() => (viewMode = 'trend')}>
        {translate($lang, 'stats_view_trend')}
      </button>
      <button class:active={viewMode === 'timeline'} onclick={() => (viewMode = 'timeline')}>
        {translate($lang, 'stats_view_timeline')}
      </button>
    </div>
  </div>
  <!-- Always rendered (nbsp until the first load) so the layout doesn't
       jump when the caption appears. -->
  <p class="refresh-caption">{refreshCaption || '\u00a0'}</p>

  <!-- KPI cards + "Where time was lost" are Overview-only. -->
  {#if viewMode === 'overview'}
    <KpiRow {totals} {comparison} target={productivityTarget} lang={$lang} />
    <ParetoChart {totals} lang={$lang} />
  {/if}

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
    {#if viewMode === 'overview'}
      {#if recordingEnabled === false}
        <p class="recording-off-note">{translate($lang, 'stats_live_recording_off')}</p>
      {:else if loadError}
        <p class="error">{loadError}</p>
      {:else}
        <SnapshotChart {machines} lang={$lang} theme={$theme} />
      {/if}
    {:else if viewMode === 'timeline'}
      <TimelineView date={selectedDate} lang={$lang} />
    {:else if rangeError}
      <p class="error">{rangeError}</p>
    {:else}
      <div class="trend-grid">
        <TrendLineChart title={translate($lang, 'stats_metric_baking')} series={bakingSeries} lang={$lang} theme={$theme} />
        <TrendLineChart title={translate($lang, 'stats_metric_waiting')} series={waitingSeries} lang={$lang} theme={$theme} />
        <TrendLineChart title={translate($lang, 'stats_metric_error')} series={errorSeries} lang={$lang} theme={$theme}>
          <Sparkline
            points={errorCountSpark}
            label={translate($lang, 'stats_sparkline_error_count')}
            color="var(--state-error)"
          />
        </TrendLineChart>
        <TrendLineChart
          title={translate($lang, 'stats_metric_productivity')}
          series={productivitySeries}
          isPercent
          lang={$lang}
          theme={$theme}
        >
          <Sparkline
            points={productivitySpark}
            label={translate($lang, 'stats_sparkline_productivity')}
            format={(v) => `${v.toFixed(1)}%`}
            color="var(--state-baking)"
          />
        </TrendLineChart>
      </div>
    {/if}
  </div>

  <!-- Technical caveat — Service level only (same tier that sees IPs /
       node IDs), not Production/Management. -->
  {#if $auth.level === 'service'}
    <p class="output-note">{translate($lang, 'stats_output_note')}</p>
  {/if}

  <!-- Headers always render, regardless of viewMode/loadError/empty data —
       only the tbody content varies. A missing/empty date shouldn't take
       the table structure away with it; the "no data" message belongs
       inside the table, not in place of it. -->
  <div class="table-area" bind:this={tableAreaEl}>
    {#if openMenu === 'columns'}
      <div class="column-popover" style:top="{columnMenuPos.top}px" style:right="{columnMenuPos.right}px">
        {#each availableColumns as col (col.key)}
          <label class="column-option" class:locked={col.locked}>
            <input
              type="checkbox"
              checked={col.locked || !$statsHiddenColumns.includes(col.key)}
              disabled={col.locked}
              onchange={() => toggleColumn(col.key)}
            />
            {translate($lang, col.labelKey)}
          </label>
        {/each}
      </div>
    {/if}
    <div class="table-wrap" onscroll={closeColumnMenu}>
      <table>
        <thead>
          <tr>
            {#each columns as col (col.key)}
              <th>
                <button type="button" class="sort-header" onclick={() => toggleSort(col.key)}>
                  {translate($lang, col.labelKey)}{sortArrow(col.key)}
                </button>
              </th>
            {/each}
            <th class="picker-th">
              <button
                type="button"
                class="picker-button"
                aria-haspopup="true"
                aria-expanded={openMenu === 'columns'}
                aria-label={translate($lang, 'stats_columns')}
                title={translate($lang, 'stats_columns')}
                onclick={toggleColumnMenu}
              >
                <!-- sliders icon -->
                <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
                  <path d="M4 6h16M4 12h16M4 18h16" />
                  <circle cx="16" cy="6" r="2" />
                  <circle cx="10" cy="12" r="2" />
                  <circle cx="18" cy="18" r="2" />
                </svg>
              </button>
            </th>
          </tr>
        </thead>
        <tbody>
          {#if loadError}
            <tr><td colspan={columns.length + 1} class="table-message error">{loadError}</td></tr>
          {:else if machines.length === 0}
            <tr><td colspan={columns.length + 1} class="table-message">{translate($lang, 'stats_no_data')}</td></tr>
          {:else}
            {#each groupedRows as group (group.name)}
              <tr class="group-row"><td colspan={columns.length + 1}>{group.name}</td></tr>
              {#each group.rows as m (m.plc_ip)}
                <tr class:worst-row={m.plc_ip === worstPlcIp} class:best-row={m.plc_ip === bestPlcIp}>
                  {#each columns as col (col.key)}
                    <td class:num={col.kind !== 'unit' && col.kind !== 'text'}>{cellText(col, m, $lang)}</td>
                  {/each}
                  <td></td>
                </tr>
              {/each}
            {/each}
          {/if}
        </tbody>
      </table>
    </div>
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
    margin-bottom: 0.4rem; /* the refresh caption sits right under it */
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

  .menu-wrap {
    position: relative;
  }

  .export-button {
    font-size: var(--font-toggle);
    font-weight: 600;
    padding: clamp(0.5rem, 1vh, 0.75rem) clamp(1rem, 1.6vw, 1.5rem);
    border: none;
    border-radius: var(--radius);
    background: var(--opelka-blue);
    color: var(--opelka-blue-fg);
    white-space: nowrap;
    cursor: pointer;
  }

  .picker-th {
    width: 1%;
    text-align: right;
    padding: 0 0.25rem;
  }

  .picker-button {
    display: inline-grid;
    place-items: center;
    padding: 0.3rem;
    border: none;
    border-radius: var(--radius);
    background: none;
    color: var(--text-secondary);
    cursor: pointer;
  }

  .picker-button:hover,
  .picker-button[aria-expanded='true'] {
    color: var(--text-primary);
    background: color-mix(in srgb, var(--opelka-blue) 14%, transparent);
  }

  .picker-button svg {
    fill: none;
    stroke: currentColor;
    stroke-width: 2;
    stroke-linecap: round;
  }

  .picker-button svg circle {
    fill: var(--bg-panel);
  }

  .table-area {
    position: relative;
  }

  /* Floats over the table (absolute, z-index) — never in the flow. */
  .column-popover {
    position: absolute;
    z-index: 30;
    display: flex;
    flex-direction: column;
    width: max-content;
    max-width: 16rem;
    max-height: min(60vh, 22rem);
    overflow-y: auto;
    padding: 0.25rem 0;
    background: var(--bg-panel);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.25);
  }

  .column-popover .column-option {
    gap: 0.5rem;
    padding: 0.3rem 0.75rem;
    font-size: var(--font-tile-sub);
  }

  .menu {
    position: absolute;
    top: calc(100% + 0.3rem);
    left: 0;
    z-index: 20;
    min-width: 11rem;
    display: flex;
    flex-direction: column;
    padding: 0.35rem 0;
    background: var(--bg-panel);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.25);
  }

  .menu a,
  .column-option {
    display: flex;
    align-items: center;
    gap: 0.55rem;
    padding: 0.5rem 0.9rem;
    font-size: var(--font-toggle);
    color: var(--text-primary);
    text-decoration: none;
    white-space: nowrap;
    cursor: pointer;
  }

  .menu a:hover,
  .column-option:hover {
    background: color-mix(in srgb, var(--opelka-blue) 14%, transparent);
  }

  .column-option.locked {
    color: var(--text-secondary);
    cursor: default;
  }

  .refresh-caption {
    margin: 0 0 clamp(1rem, 2vh, 1.75rem);
    font-size: calc(var(--font-tile-sub) * 0.85);
    color: var(--text-secondary);
    opacity: 0.8;
    font-variant-numeric: tabular-nums;
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
    padding: 0;
  }

  .sort-header {
    width: 100%;
    padding: clamp(0.4rem, 0.8vh, 0.65rem) clamp(0.6rem, 1vw, 1rem);
    background: none;
    border: none;
    color: inherit;
    font: inherit;
    font-weight: 600;
    text-align: left;
    cursor: pointer;
    white-space: nowrap;
  }

  .sort-header:hover {
    color: var(--text-primary);
  }

  .group-row td {
    font-size: var(--font-group-header);
    font-weight: 700;
    color: var(--text-primary);
    /* Breathing room above and below so the group name reads as its own
       section label rather than being squeezed between rows. */
    padding-top: clamp(0.75rem, 1.5vh, 1.1rem);
    padding-bottom: clamp(0.3rem, 0.6vh, 0.45rem);
    border-bottom: 2px solid var(--border-color);
  }

  tbody tr:first-child.group-row td {
    padding-top: clamp(0.5rem, 1vh, 0.75rem);
  }

  /* Subtle tints (not solid fills, which would clash with the row's own
     text colour) flagging the day's single worst/best performer — see
     Statistics.svelte's worstPlcIp/bestPlcIp docstring for when these
     apply. */
  .worst-row td {
    background: color-mix(in srgb, var(--danger-bg) 12%, transparent);
  }

  .best-row td {
    background: color-mix(in srgb, var(--state-baking) 12%, transparent);
  }
</style>
