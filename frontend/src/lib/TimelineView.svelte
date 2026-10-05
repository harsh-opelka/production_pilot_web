<script>
  // "Timeline" view mode (see Statistics.svelte) — one horizontal band per
  // machine, built from GET /api/stats/timeline's per-PLC state spans.
  // Follows the same today-vs-past refresh rule established for the
  // Overview tab in Stage 1: today auto-refreshes every 30s, a past date
  // fetches once.
  import { translate } from './translations.js';
  import { formatUnitLabel, todayLocalDate } from './format.js';
  import { getTimeline, ServiceApiError } from './serviceApi.js';

  let { date, lang = 'en' } = $props();

  const REFRESH_MS = 30_000;

  let machines = $state([]);
  let loadError = $state('');
  let loading = $state(true);

  $effect(() => {
    const d = date;
    const isToday = d === todayLocalDate();
    loadError = '';
    loading = true;

    async function load() {
      try {
        const data = await getTimeline(d);
        if (d !== date) return;
        machines = data.machines;
        loadError = '';
      } catch (err) {
        if (d !== date) return;
        machines = [];
        loadError = err instanceof ServiceApiError ? err.message : String(err);
      } finally {
        if (d === date) loading = false;
      }
    }

    load();
    if (!isToday) return; // past date: fetch once, no auto-refresh
    const interval = setInterval(load, REFRESH_MS);
    return () => clearInterval(interval);
  });

  // Day-start (local midnight) and the axis' end instant — "now" for
  // today, local midnight the FOLLOWING day otherwise (see
  // stats.compute_timeline's docstring). Both are real Date instants
  // (not a fixed 86400s) so a DST-shifted day doesn't skew placement.
  let dayStart = $derived.by(() => {
    const [y, mo, d] = date.split('-').map(Number);
    return new Date(y, mo - 1, d, 0, 0, 0, 0);
  });
  let axisEnd = $derived.by(() => {
    if (date === todayLocalDate()) return new Date();
    const s = dayStart;
    return new Date(s.getFullYear(), s.getMonth(), s.getDate() + 1);
  });
  let totalMs = $derived(Math.max(1, axisEnd.getTime() - dayStart.getTime()));

  function leftPct(isoTimestamp) {
    const t = new Date(isoTimestamp).getTime();
    const clamped = Math.min(Math.max(t, dayStart.getTime()), axisEnd.getTime());
    return ((clamped - dayStart.getTime()) / totalMs) * 100;
  }

  function segmentStyle(span) {
    const left = leftPct(span.start);
    const width = Math.max(0, leftPct(span.end) - left);
    return `left: ${left}%; width: ${width}%;`;
  }

  // Offline spans render as a distinct "Offline" visual (same as the
  // Dashboard's FryerTile treatment) rather than whatever last-known
  // state they carry — a manager scanning the band cares "was this PLC
  // reachable", not a possibly-stale state name. NO_DATA (server not
  // observing at all) is visually distinct again from both — see
  // .seg-no-data's hatched pattern below.
  function stateClass(span) {
    if (span.state === 'NO_DATA') return 'seg-no-data';
    if (span.is_online === false) return 'seg-offline';
    return `seg-${span.state.toLowerCase()}`;
  }

  function durationLabel(span) {
    const totalSec = Math.max(0, Math.round((new Date(span.end) - new Date(span.start)) / 1000));
    const h = Math.floor(totalSec / 3600);
    const m = Math.round((totalSec % 3600) / 60);
    return translate(lang, 'kpi_hm_format', { h, m });
  }

  function tooltipText(span) {
    const label =
      span.state === 'NO_DATA'
        ? translate(lang, 'stats_timeline_no_data')
        : span.is_online === false
          ? translate(lang, 'status_offline')
          : translate(lang, `state_${span.state.toLowerCase()}`);
    const startTime = new Date(span.start).toLocaleTimeString(lang === 'de' ? 'de-DE' : 'en-US', {
      hour: '2-digit',
      minute: '2-digit',
    });
    return `${label} — ${startTime} (${durationLabel(span)})`;
  }

  // Hour tick marks along the shared axis (every 2h, to stay legible) —
  // purely visual, positioned the same way as segments.
  let hourTicks = $derived.by(() => {
    const ticks = [];
    for (let h = 0; h <= 24; h += 2) {
      const t = new Date(dayStart.getFullYear(), dayStart.getMonth(), dayStart.getDate(), h, 0, 0, 0);
      if (t > axisEnd) break;
      ticks.push({ hour: h, pct: ((t.getTime() - dayStart.getTime()) / totalMs) * 100 });
    }
    return ticks;
  });

  const LEGEND_ITEMS = [
    { key: 'ready', labelKey: 'state_ready' },
    { key: 'baking', labelKey: 'state_baking' },
    { key: 'heating', labelKey: 'state_heating' },
    { key: 'cold', labelKey: 'state_cold' },
    { key: 'error', labelKey: 'state_error' },
    { key: 'offline', labelKey: 'status_offline' },
  ];
</script>

<div class="timeline-view">
  {#if loadError}
    <p class="error">{loadError}</p>
  {:else if !loading && machines.length === 0}
    <p class="table-message">{translate(lang, 'stats_no_data')}</p>
  {:else if machines.length > 0}
    <div class="axis-row">
      <div class="axis-spacer"></div>
      <div class="axis-track">
        {#each hourTicks as tick (tick.hour)}
          <span class="axis-tick" style:left="{tick.pct}%">{String(tick.hour).padStart(2, '0')}:00</span>
        {/each}
      </div>
    </div>

    <div class="bands">
      {#each machines as m (m.plc_ip)}
        <div class="band-row">
          <div class="band-label">{m.group_name} — {formatUnitLabel(m.unit_number, lang)}</div>
          <div class="band-track">
            {#each m.spans as span, i (i)}
              <div class="segment {stateClass(span)}" style={segmentStyle(span)}>
                <div class="tooltip">{tooltipText(span)}</div>
              </div>
            {/each}
          </div>
        </div>
      {/each}
    </div>

    <div class="legend">
      {#each LEGEND_ITEMS as item (item.key)}
        <div class="legend-item">
          <span class="dot seg-{item.key}"></span>
          <span class="label">{translate(lang, item.labelKey)}</span>
        </div>
      {/each}
      <div class="legend-item">
        <span class="dot seg-no-data"></span>
        <span class="label">{translate(lang, 'stats_timeline_no_data')}</span>
      </div>
    </div>
  {/if}
</div>

<style>
  .timeline-view {
    display: flex;
    flex-direction: column;
    gap: clamp(0.5rem, 1vh, 0.75rem);
  }

  .axis-row,
  .band-row {
    display: grid;
    grid-template-columns: minmax(8rem, 14rem) 1fr;
    align-items: center;
    gap: clamp(0.5rem, 1vw, 1rem);
  }

  .axis-track {
    position: relative;
    height: 1.4rem;
  }

  .axis-tick {
    position: absolute;
    top: 0;
    transform: translateX(-50%);
    font-size: 0.7rem;
    color: var(--text-secondary);
    white-space: nowrap;
  }

  .bands {
    display: flex;
    flex-direction: column;
    gap: clamp(0.4rem, 0.8vh, 0.6rem);
  }

  .band-label {
    font-size: var(--font-toggle);
    color: var(--text-primary);
    overflow-wrap: break-word;
  }

  .band-track {
    position: relative;
    height: clamp(1.6rem, 3vh, 2.2rem);
    background: var(--bg-app);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    overflow: hidden;
  }

  .segment {
    position: absolute;
    top: 0;
    bottom: 0;
    transition: filter 0.1s;
  }

  .segment:hover {
    filter: brightness(1.2);
    z-index: 2;
  }

  .tooltip {
    position: absolute;
    bottom: 100%;
    left: 50%;
    transform: translateX(-50%);
    margin-bottom: 0.35rem;
    background: var(--bg-panel);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    padding: 0.3rem 0.55rem;
    font-size: 0.75rem;
    color: var(--text-primary);
    white-space: nowrap;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.1s;
    z-index: 5;
  }

  .segment:hover .tooltip {
    opacity: 1;
  }

  .seg-ready {
    background: var(--state-ready);
  }

  .seg-baking {
    background: var(--state-baking);
  }

  .seg-heating {
    background: var(--state-heating);
  }

  .seg-cold {
    background: var(--state-cold);
  }

  .seg-error {
    background: var(--state-error);
  }

  .seg-offline {
    background: var(--offline-bg);
    border-left: 1px dashed var(--offline-border);
    border-right: 1px dashed var(--offline-border);
  }

  /* Deliberately distinct from the solid grey .seg-cold — a diagonal
     hatch over a muted background so "we weren't recording" can never be
     mistaken for a real Cold reading (see this component's docstring). */
  .seg-no-data {
    background-color: var(--bg-panel);
    background-image: repeating-linear-gradient(
      45deg,
      var(--text-secondary) 0,
      var(--text-secondary) 2px,
      transparent 2px,
      transparent 8px
    );
    opacity: 0.6;
  }

  .legend {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 1.25rem;
    padding-top: 0.25rem;
  }

  .legend-item {
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }

  .dot {
    width: 0.85rem;
    height: 0.65rem;
    border-radius: 3px;
    flex-shrink: 0;
  }

  .legend .label {
    font-size: 0.75rem;
    color: var(--text-secondary);
    white-space: nowrap;
  }

  .table-message {
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
</style>
