<script>
  import Chart, { cssVar } from './chartSetup.js';
  import { translate } from './translations.js';
  import { formatUnitLabel } from './format.js';

  let { machines = [], lang = 'en', theme = 'dark' } = $props();

  // Productivity is a % (0-100), not minutes, so it can't share the left
  // axis with the three time-based bars without either dwarfing them or
  // being invisible next to them. Plotting it against a separate right-
  // hand axis (fixed 0-100) keeps both readable on one chart without
  // implying a false relationship between the two scales — the two axes'
  // gridlines are also kept from overlapping (right axis draws no grid of
  // its own) so it's clear at a glance which axis a bar belongs to.
  const PRODUCTIVITY_COLOR = '#7c3aed';

  let canvasEl;
  let chart;

  $effect(() => {
    const data = machines;
    const language = lang;
    // theme isn't read directly below, but --text-secondary/--border-color
    // resolve differently per theme, so this must still be a dependency —
    // touching it here is what makes the effect re-run on a theme switch.
    void theme;

    if (!canvasEl) return;

    const textColor = cssVar('--text-secondary');
    const gridColor = cssVar('--border-color');
    const bakingColor = cssVar('--state-baking');
    const waitingColor = cssVar('--state-ready');
    const errorColor = cssVar('--state-error');

    const labels = data.map((m) => `${m.group_name} — ${formatUnitLabel(m.unit_number, language)}`);

    const next = new Chart(canvasEl, {
      type: 'bar',
      data: {
        labels,
        datasets: [
          {
            label: translate(language, 'stats_metric_baking'),
            data: data.map((m) => m.baking_seconds / 60),
            backgroundColor: bakingColor,
            yAxisID: 'minutes',
          },
          {
            label: translate(language, 'stats_metric_waiting'),
            data: data.map((m) => m.ready_seconds / 60),
            backgroundColor: waitingColor,
            yAxisID: 'minutes',
          },
          {
            label: translate(language, 'stats_metric_error'),
            data: data.map((m) => m.error_seconds / 60),
            backgroundColor: errorColor,
            yAxisID: 'minutes',
          },
          {
            label: translate(language, 'stats_metric_productivity'),
            data: data.map((m) => m.productivity_pct),
            backgroundColor: PRODUCTIVITY_COLOR,
            yAxisID: 'pct',
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: textColor } },
        },
        scales: {
          x: {
            ticks: { color: textColor },
            grid: { color: gridColor },
          },
          minutes: {
            type: 'linear',
            position: 'left',
            beginAtZero: true,
            title: { display: true, text: translate(language, 'stats_axis_minutes'), color: textColor },
            ticks: { color: textColor },
            grid: { color: gridColor },
          },
          pct: {
            type: 'linear',
            position: 'right',
            beginAtZero: true,
            max: 100,
            title: { display: true, text: '%', color: textColor },
            ticks: { color: textColor },
            grid: { drawOnChartArea: false },
          },
        },
      },
    });

    chart = next;
    return () => next.destroy();
  });
</script>

<div class="chart-box">
  <canvas bind:this={canvasEl}></canvas>
</div>

<style>
  .chart-box {
    position: relative;
    height: clamp(16rem, 40vh, 26rem);
    background: var(--bg-panel);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    padding: clamp(0.5rem, 1vh, 1rem);
  }
</style>
