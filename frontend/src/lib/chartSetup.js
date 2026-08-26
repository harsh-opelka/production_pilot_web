// Single import point for Chart.js — `chart.js/auto` auto-registers every
// controller/element/scale/plugin, which is the simplest option for a
// small internal app (no bundle-size pressure) and avoids manually
// tracking which pieces each chart type needs. Global font is set once
// here so every chart matches the rest of the app (see the DejaVu Sans
// task) without each chart component repeating it.
import Chart from 'chart.js/auto';

Chart.defaults.font.family = "'DejaVu Sans', Verdana, Arial, sans-serif";

export default Chart;

export function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
