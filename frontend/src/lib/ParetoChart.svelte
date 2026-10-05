<script>
  // "Where time was lost" — a simple horizontal bar-list (not a Chart.js
  // canvas like SnapshotChart/TrendLineChart) since what's needed here is
  // precise inline "Xh Ym (NN%)" text per bar, which a bare Chart.js bar
  // chart can't place without an extra datalabels plugin — plain
  // flexbox bars sized by percentage give full control over that text for
  // free, with no new dependency. Baking is deliberately excluded (see
  // Statistics.svelte's docstring on this component) — this chart is
  // about LOSS categories, not the full state breakdown. Offline is also
  // excluded: it's a connectivity issue, not a production-loss category.
  import { translate } from './translations.js';
  import { formatHoursMinutes } from './format.js';

  let { totals = null, lang = 'en' } = $props();

  const CATEGORIES = [
    { key: 'error_seconds', labelKey: 'stats_metric_error', colorVar: '--state-error' },
    { key: 'ready_seconds', labelKey: 'stats_metric_waiting', colorVar: '--state-ready' },
    { key: 'cold_seconds', labelKey: 'stats_col_cold', colorVar: '--state-cold' },
  ];

  let bars = $derived.by(() => {
    if (!totals) return [];
    const rows = CATEGORIES.map((c) => ({ ...c, seconds: totals[c.key] ?? 0 }));
    const total = rows.reduce((sum, r) => sum + r.seconds, 0);
    const max = Math.max(...rows.map((r) => r.seconds), 1);
    return rows
      .map((r) => ({ ...r, pct: total > 0 ? (r.seconds / total) * 100 : 0, widthPct: (r.seconds / max) * 100 }))
      .sort((a, b) => b.seconds - a.seconds);
  });

  let hasAnyLoss = $derived(bars.some((b) => b.seconds > 0));
</script>

<div class="pareto-box">
  <h3>{translate(lang, 'stats_pareto_title')}</h3>
  {#if !totals}
    <p class="empty">{translate(lang, 'stats_no_data')}</p>
  {:else if !hasAnyLoss}
    <p class="empty">{translate(lang, 'stats_pareto_empty')}</p>
  {:else}
    <div class="bars">
      {#each bars as bar (bar.key)}
        <div class="bar-row">
          <span class="bar-label">{translate(lang, bar.labelKey)}</span>
          <div class="bar-track">
            <div class="bar-fill" style:width="{bar.widthPct}%" style:background="var({bar.colorVar})"></div>
          </div>
          <span class="bar-value">{formatHoursMinutes(bar.seconds, lang)} ({bar.pct.toFixed(0)}%)</span>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .pareto-box {
    background: var(--bg-panel);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    padding: clamp(0.85rem, 1.6vh, 1.25rem);
    margin-bottom: clamp(0.75rem, 1.5vh, 1.25rem);
  }

  h3 {
    margin: 0 0 clamp(0.6rem, 1.2vh, 1rem);
    font-size: var(--font-group-header);
    color: var(--text-primary);
  }

  .empty {
    margin: 0;
    padding: clamp(1.25rem, 3vh, 2rem) 0;
    color: var(--text-secondary);
    font-size: var(--font-toggle);
    text-align: center;
  }

  .bars {
    display: flex;
    flex-direction: column;
    gap: clamp(0.5rem, 1vh, 0.75rem);
  }

  .bar-row {
    display: grid;
    grid-template-columns: minmax(6rem, 9rem) 1fr minmax(6rem, auto);
    align-items: center;
    gap: clamp(0.5rem, 1vw, 1rem);
  }

  .bar-label {
    font-size: var(--font-toggle);
    color: var(--text-secondary);
    overflow-wrap: break-word;
  }

  .bar-track {
    background: var(--bg-app);
    border-radius: var(--radius);
    height: clamp(0.85rem, 1.6vh, 1.25rem);
    overflow: hidden;
  }

  .bar-fill {
    height: 100%;
    border-radius: var(--radius);
    transition: width 0.2s;
  }

  .bar-value {
    font-size: var(--font-toggle);
    font-weight: 600;
    color: var(--text-primary);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
    text-align: right;
  }
</style>
