<script>
  import Chart, { cssVar } from './chartSetup.js';

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

  let { title = '', series = [], isPercent = false, theme = 'dark' } = $props();

  let canvasEl;

  $effect(() => {
    const data = series;
    const percent = isPercent;
    const heading = title;
    void theme; // see SnapshotChart.svelte — re-resolves theme-dependent colours below

    if (!canvasEl) return;

    const textColor = cssVar('--text-secondary');
    const gridColor = cssVar('--border-color');

    const labels = data[0]?.points.map((p) => p.date) ?? [];

    const next = new Chart(canvasEl, {
      type: 'line',
      data: {
        labels,
        datasets: data.map((s, i) => ({
          label: s.label,
          data: s.points.map((p) => p.value),
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
  <canvas bind:this={canvasEl}></canvas>
</div>

<style>
  .chart-box {
    position: relative;
    height: clamp(14rem, 32vh, 20rem);
    background: var(--bg-panel);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    padding: clamp(0.5rem, 1vh, 1rem);
  }
</style>
