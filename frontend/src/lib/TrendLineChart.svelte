<script>
  import Chart, { cssVar } from './chartSetup.js';
  import { translate } from './translations.js';
  import { pickDurationUnit } from './format.js';

  // series: [{ label, points: [{ date, value: number|null }] }]
  // One chart per metric (see Statistics.svelte), one line per machine —
  // so colour here identifies a MACHINE, not a state. Deliberately not
  // drawn from the green/blue/red/amber state palette used elsewhere
  // (SnapshotChart, dashboard tiles): a machine's line colour has nothing
  // to do with any particular state, and reusing e.g. red for a machine
  // would misleadingly suggest "this machine = error".
  const MACHINE_PALETTE = [
    '#7c3aed', // violet
    '#0891b2', // cyan
    '#db2777', // pink
    '#a16207', // dark amber/brown
    '#4338ca', // indigo
    '#0d9488', // teal
    '#be185d', // magenta
    '#65a30d', // lime
  ];

  // `children`: optional strip rendered above the canvas (the Trend tab's
  // 7-day sparklines — see Statistics.svelte).
  let { title = '', series = [], isPercent = false, theme = 'dark', lang = 'en', children } = $props();

  let canvasEl;

  $effect(() => {
    const data = series;
    const percent = isPercent;
    const heading = title;
    const language = lang;
    void theme; // see SnapshotChart.svelte — re-resolves theme-dependent colours below

    if (!canvasEl) return;

    const textColor = cssVar('--text-secondary');
    const gridColor = cssVar('--border-color');

    const labels = data[0]?.points.map((p) => p.date) ?? [];

    // Series carry raw seconds (see Statistics.svelte's buildSeries) for
    // duration metrics, so — like SnapshotChart — the axis unit is picked
    // from the largest value actually plotted rather than being fixed to
    // "Minutes". Percent metrics (productivity) are never seconds and
    // keep their fixed 0-100 axis untouched.
    const allValues = data.flatMap((s) => s.points.map((p) => p.value)).filter((v) => v != null);
    const maxValue = allValues.length ? Math.max(...allValues) : 0;
    const { divisor, labelKey } = percent ? { divisor: 1, labelKey: null } : pickDurationUnit(maxValue);

    const next = new Chart(canvasEl, {
      type: 'line',
      data: {
        labels,
        datasets: data.map((s, i) => ({
          label: s.label,
          data: s.points.map((p) => (p.value == null ? null : p.value / divisor)),
          borderColor: MACHINE_PALETTE[i % MACHINE_PALETTE.length],
          backgroundColor: MACHINE_PALETTE[i % MACHINE_PALETTE.length],
          // Missing days are `null`, not 0 (see Statistics.svelte) — with
          // spanGaps left at its default (true) Chart.js would draw a
          // straight line straight through a gap as if the day had been
          // measured at some in-between value. false makes the line
          // actually break there, an honest "we don't know" instead of
          // invented interpolation.
          spanGaps: false,
          tension: 0.15,
        })),
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          title: { display: true, text: heading, color: textColor },
          legend: { labels: { color: textColor } },
        },
        scales: {
          x: {
            ticks: { color: textColor },
            grid: { color: gridColor },
          },
          y: {
            beginAtZero: true,
            max: percent ? 100 : undefined,
            title: { display: true, text: percent ? '%' : translate(language, labelKey), color: textColor },
            ticks: { color: textColor },
            grid: { color: gridColor },
          },
        },
      },
    });

    return () => next.destroy();
  });
</script>

<div class="chart-box">
  {#if children}
    <div class="chart-extra">{@render children()}</div>
  {/if}
  <div class="canvas-wrap">
    <canvas bind:this={canvasEl}></canvas>
  </div>
</div>

<style>
  .chart-box {
    display: flex;
    flex-direction: column;
    height: clamp(14rem, 32vh, 20rem);
    background: var(--bg-panel);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    padding: clamp(0.5rem, 1vh, 1rem);
  }

  .chart-extra {
    display: flex;
    justify-content: flex-end;
    padding-bottom: 0.4rem;
    border-bottom: 1px solid var(--border-color);
    margin-bottom: 0.4rem;
  }

  /* Chart.js's responsive sizing needs a positioned parent whose height
     it doesn't itself drive — min-height: 0 lets it shrink in the flex
     column when the sparkline strip is present. */
  .canvas-wrap {
    position: relative;
    flex: 1;
    min-height: 0;
  }
</style>
