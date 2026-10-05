<script>
  // Tiny inline-SVG trend line for the Trend tab's per-metric panels (see
  // Statistics.svelte) — plain SVG rather than another Chart.js canvas,
  // since it has no axes/legend/tooltips to speak of. `points` is
  // [{ date, value: number|null }]; null is a day with no recorded data
  // and breaks the line (same honest-gap rule as TrendLineChart).
  let { points = [], label = '', format = (v) => String(v), color = 'var(--opelka-blue)' } = $props();

  const W = 120;
  const H = 32;
  const PAD = 3;

  let geometry = $derived.by(() => {
    const values = points.map((p) => p.value).filter((v) => v != null);
    if (!values.length) return null;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || 1;
    const step = points.length > 1 ? (W - 2 * PAD) / (points.length - 1) : 0;
    const xy = points.map((p, i) =>
      p.value == null ? null : [PAD + i * step, H - PAD - ((p.value - min) / span) * (H - 2 * PAD)],
    );

    // Split into runs of consecutive non-null points.
    const runs = [];
    let run = [];
    for (const pt of xy) {
      if (pt) run.push(pt);
      else if (run.length) (runs.push(run), (run = []));
    }
    if (run.length) runs.push(run);

    const lastIndex = xy.findLastIndex((pt) => pt != null);
    return {
      paths: runs.map((r) => r.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`).join('')),
      last: xy[lastIndex],
      lastValue: points[lastIndex].value,
    };
  });
</script>

<div class="sparkline" title={label}>
  <span class="spark-label">{label}</span>
  {#if geometry}
    <svg viewBox="0 0 {W} {H}" aria-hidden="true">
      {#each geometry.paths as d}
        <path {d} style:stroke={color} />
      {/each}
      <circle cx={geometry.last[0]} cy={geometry.last[1]} r="2.5" style:fill={color} />
    </svg>
    <span class="spark-value">{format(geometry.lastValue)}</span>
  {:else}
    <span class="spark-value empty">–</span>
  {/if}
</div>

<style>
  .sparkline {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    font-size: var(--font-tile-sub);
    color: var(--text-secondary);
    min-width: 0;
  }

  .spark-label {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  svg {
    width: 7.5rem;
    height: 2rem;
    flex-shrink: 0;
    overflow: visible;
  }

  path {
    fill: none;
    stroke-width: 2;
    stroke-linejoin: round;
    stroke-linecap: round;
    vector-effect: non-scaling-stroke;
  }

  .spark-value {
    font-weight: 700;
    color: var(--text-primary);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }

  .spark-value.empty {
    color: var(--text-secondary);
  }
</style>
