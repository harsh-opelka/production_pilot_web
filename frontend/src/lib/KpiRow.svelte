<script>
  // Headline KPI cards for the Statistics page (see Statistics.svelte).
  // `totals`/`comparison` are the "totals"/"comparison" fields of
  // GET /api/stats/daily-summary?compare=avg_7d — comparison is null when
  // none of the 7 days before the selected date has recorded data (see
  // stats.compute_seven_day_average's docstring), never a fake all-zero
  // average. Productivity is compared against `target` (app_settings'
  // productivity_target_pct) instead of the average.
  import { translate } from './translations.js';
  import { formatHoursMinutes } from './format.js';

  let { totals = null, comparison = null, target = null, lang = 'en' } = $props();

  // --- Status thresholds (left accent border colour) — tune here ----------
  // Productivity (vs target):
  //   green  >= target
  //   amber  within PRODUCTIVITY_AMBER_PTS percentage points below target
  //   red    more than that below target
  const PRODUCTIVITY_AMBER_PTS = 10;
  // Error time / error count (vs 7-day avg; lower is better):
  //   green  improved by more than the "on par" tolerance, or zero today
  //   amber  within ±tolerance of the average ("on par")
  //   red    worse by more than the tolerance
  // Baking time (vs 7-day avg; higher is better):
  //   green  no more than FLAT_BAND below the average (on par or better)
  //   amber  FLAT_BAND .. BAKING_RED_BAND below the average
  //   red    more than BAKING_RED_BAND below the average
  // Tolerance = FLAT_BAND of the average, but never below the absolute
  // floors, so a near-zero average doesn't turn one error into "red".
  const FLAT_BAND = 0.05; // ±5 %
  const BAKING_RED_BAND = 0.15; // 15 %
  const MIN_TOLERANCE_ERROR_SECONDS = 60;
  const MIN_TOLERANCE_ERROR_COUNT = 0.5;

  function tolerance(avg, floor) {
    return Math.max(Math.abs(avg) * FLAT_BAND, floor);
  }

  // Direction word ("improved"/"worse"/"on par") + arrow for a delta vs
  // the average. higherIsBetter=false for the two loss metrics.
  function trend(delta, tol, higherIsBetter) {
    const arrow = delta > 0 ? '▲' : delta < 0 ? '▼' : '';
    if (Math.abs(delta) <= tol) return { arrow, word: 'stats_kpi_on_par' };
    const good = higherIsBetter ? delta > 0 : delta < 0;
    return { arrow, word: good ? 'stats_kpi_improved' : 'stats_kpi_worse' };
  }

  function lossStatus(current, delta, tol) {
    if (current === 0 || delta < -tol) return 'good';
    return delta > tol ? 'bad' : 'watch';
  }

  function bakingStatus(delta, avg) {
    if (delta >= -Math.max(avg * FLAT_BAND, 0)) return 'good';
    return delta >= -avg * BAKING_RED_BAND ? 'watch' : 'bad';
  }

  function fmtCount(n) {
    const abs = Math.abs(n);
    return Number.isInteger(abs) ? String(abs) : abs.toFixed(1);
  }

  // --- Productivity (vs target) ---------------------------------------------
  let productivity = $derived.by(() => {
    if (!totals) return null;
    const pct = totals.productivity_pct;
    if (target == null) return { pct, status: 'none', deltaPts: null };
    const deltaPts = Math.round((pct - target) * 10) / 10;
    const status = deltaPts >= 0 ? 'good' : deltaPts >= -PRODUCTIVITY_AMBER_PTS ? 'watch' : 'bad';
    return { pct, status, deltaPts };
  });

  // Progress ring geometry (SVG units, viewBox 0 0 100 100).
  const RING_R = 42;
  const RING_C = 2 * Math.PI * RING_R;
  let ringDash = $derived(productivity ? (Math.min(100, Math.max(0, productivity.pct)) / 100) * RING_C : 0);
  // Target tick across the ring, measured clockwise from 12 o'clock.
  let targetTick = $derived.by(() => {
    if (target == null) return null;
    const a = (Math.min(100, Math.max(0, target)) / 100) * 2 * Math.PI - Math.PI / 2;
    const r1 = RING_R - 8;
    const r2 = RING_R + 8;
    return {
      x1: 50 + r1 * Math.cos(a),
      y1: 50 + r1 * Math.sin(a),
      x2: 50 + r2 * Math.cos(a),
      y2: 50 + r2 * Math.sin(a),
    };
  });

  // --- Baking / error time / error count (vs 7-day avg) ---------------------
  let baking = $derived.by(() => {
    if (!totals || !comparison) return null;
    const avg = comparison.averages.baking_seconds;
    const delta = comparison.deltas.baking_seconds;
    return {
      status: bakingStatus(delta, avg),
      ...trend(delta, avg * FLAT_BAND, true),
      text: formatHoursMinutes(Math.abs(delta), lang),
    };
  });

  let errorTime = $derived.by(() => {
    if (!totals || !comparison) return null;
    const delta = comparison.deltas.error_seconds;
    const tol = tolerance(comparison.averages.error_seconds, MIN_TOLERANCE_ERROR_SECONDS);
    return {
      status: lossStatus(totals.error_seconds, delta, tol),
      ...trend(delta, tol, false),
      text: formatHoursMinutes(Math.abs(delta), lang),
    };
  });

  let errorCount = $derived.by(() => {
    if (!totals || !comparison) return null;
    const delta = comparison.deltas.error_count;
    const tol = tolerance(comparison.averages.error_count, MIN_TOLERANCE_ERROR_COUNT);
    return {
      status: lossStatus(totals.error_count, delta, tol),
      ...trend(delta, tol, false),
      text: fmtCount(delta),
    };
  });
</script>

{#snippet avgDelta(info)}
  {#if info}
    <span class="kpi-delta {info.status}">
      {info.arrow} {info.text}, {translate(lang, info.word)}
    </span>
    <span class="kpi-basis">{translate(lang, 'stats_kpi_vs_avg')}</span>
  {:else if totals}
    <span class="kpi-delta none">{translate(lang, 'stats_kpi_no_comparison')}</span>
  {/if}
{/snippet}

<div class="kpi-row">
  <div class="kpi-card status-{productivity?.status ?? 'none'}">
    <span class="kpi-label">{translate(lang, 'stats_kpi_productivity')}</span>
    <div class="ring-wrap">
      <svg class="ring" viewBox="0 0 100 100" role="img" aria-label="{totals ? productivity.pct.toFixed(1) : '–'}%">
        <circle class="ring-track" cx="50" cy="50" r={RING_R} />
        {#if productivity}
          <circle
            class="ring-progress"
            cx="50"
            cy="50"
            r={RING_R}
            stroke-dasharray="{ringDash} {RING_C}"
            transform="rotate(-90 50 50)"
          />
        {/if}
        {#if targetTick}
          <line class="ring-target" x1={targetTick.x1} y1={targetTick.y1} x2={targetTick.x2} y2={targetTick.y2} />
        {/if}
      </svg>
      <span class="ring-value">{productivity ? `${productivity.pct.toFixed(1)}%` : '–'}</span>
    </div>
    {#if productivity && productivity.deltaPts != null}
      <span class="kpi-delta {productivity.status}">
        {productivity.deltaPts > 0 ? '▲' : productivity.deltaPts < 0 ? '▼' : ''}
        {translate(lang, 'stats_kpi_vs_target', { delta: Math.abs(productivity.deltaPts).toFixed(1) })}
      </span>
      <span class="kpi-basis">{translate(lang, 'stats_kpi_target', { target })}</span>
    {:else if totals}
      <span class="kpi-delta none">{translate(lang, 'stats_kpi_no_target')}</span>
    {/if}
  </div>

  <div class="kpi-card status-{baking?.status ?? 'none'}">
    <span class="kpi-label">{translate(lang, 'stats_kpi_baking')}</span>
    <span class="kpi-value">{totals ? formatHoursMinutes(totals.baking_seconds, lang) : '–'}</span>
    {@render avgDelta(baking)}
  </div>

  <div class="kpi-card status-{errorTime?.status ?? 'none'}">
    <span class="kpi-label">{translate(lang, 'stats_kpi_error_time')}</span>
    <span class="kpi-value">{totals ? formatHoursMinutes(totals.error_seconds, lang) : '–'}</span>
    {@render avgDelta(errorTime)}
  </div>

  <div class="kpi-card status-{errorCount?.status ?? 'none'}">
    <span class="kpi-label">{translate(lang, 'stats_kpi_error_count')}</span>
    <span class="kpi-value">{totals ? totals.error_count : '–'}</span>
    {@render avgDelta(errorCount)}
  </div>
</div>

<style>
  .kpi-row {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 12rem), 1fr));
    gap: clamp(0.75rem, 1.5vw, 1.25rem);
    margin-bottom: clamp(1rem, 2vh, 1.75rem);
  }

  /* Status palette: the same state colours the dashboard tiles use —
     green = baking, amber = heating, red = danger. --status-color drives
     the accent border, the delta text and the productivity ring. */
  .kpi-card {
    --status-color: var(--border-color);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    gap: 0.35rem;
    background: var(--bg-panel);
    border: 1px solid var(--border-color);
    border-left: 5px solid var(--status-color);
    border-radius: var(--radius);
    box-shadow: var(--tile-shadow);
    padding: clamp(0.9rem, 1.8vh, 1.4rem) clamp(0.75rem, 1.2vw, 1.1rem);
    min-width: 0;
  }

  .kpi-card.status-good {
    --status-color: var(--state-baking);
  }

  .kpi-card.status-watch {
    --status-color: var(--state-heating);
  }

  .kpi-card.status-bad {
    --status-color: var(--danger-bg);
  }

  .kpi-label {
    font-size: var(--font-tile-sub);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-weight: 600;
  }

  .kpi-value {
    font-size: clamp(1.6rem, 3.2vw, 2.3rem);
    font-weight: 700;
    line-height: 1.15;
    color: var(--text-primary);
    font-variant-numeric: tabular-nums;
  }

  .ring-wrap {
    position: relative;
    width: clamp(5.5rem, 9vw, 7.5rem);
    aspect-ratio: 1;
    display: grid;
    place-items: center;
  }

  .ring {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
  }

  .ring-track {
    fill: none;
    stroke: var(--border-color);
    stroke-width: 10;
  }

  .ring-progress {
    fill: none;
    stroke: var(--status-color);
    stroke-width: 10;
    stroke-linecap: round;
    transition: stroke-dasharray 0.3s;
  }

  /* Neutral (no target set) ring falls back to the brand navy rather
     than the grey border colour, so the progress still reads. */
  .status-none .ring-progress {
    stroke: var(--opelka-blue);
  }

  .ring-target {
    stroke: var(--text-primary);
    stroke-width: 2.5;
    stroke-linecap: round;
  }

  .ring-value {
    position: relative;
    font-size: clamp(1.1rem, 2vw, 1.5rem);
    font-weight: 700;
    color: var(--text-primary);
    font-variant-numeric: tabular-nums;
  }

  .kpi-delta {
    font-size: var(--font-tile-sub);
    font-weight: 600;
    color: var(--status-color);
  }

  /* Amber text is too faint on the light theme's white panel — the
     accent border already carries the "watch" signal. */
  .status-watch .kpi-delta {
    color: var(--text-primary);
  }

  .kpi-delta.none {
    color: var(--text-secondary);
    font-weight: 400;
    font-style: italic;
  }

  .kpi-basis {
    font-size: calc(var(--font-tile-sub) * 0.9);
    color: var(--text-secondary);
  }
</style>
