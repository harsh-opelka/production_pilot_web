<script>
  import { onMount, onDestroy } from 'svelte';
  import { lang } from './stores.js';

  const pad = (n) => String(n).padStart(2, '0');

  let now = $state(new Date());
  let intervalId;

  onMount(() => {
    intervalId = setInterval(() => {
      now = new Date();
    }, 30_000);
  });

  onDestroy(() => clearInterval(intervalId));

  let dateStr = $derived(`${pad(now.getDate())}.${pad(now.getMonth() + 1)}.${now.getFullYear()}`);
  let timeStr = $derived(`${pad(now.getHours())}:${pad(now.getMinutes())}${$lang === 'de' ? ' Uhr' : ''}`);
</script>

<footer class="app-footer">
  <span class="line">Produktionspilot 1.0 | OPELKA GmbH | {dateStr} | {timeStr}</span>
</footer>

<style>
  /* Fixed px sizing everywhere (not rem/clamp) — this footer is deliberately
     exempt from the --ui-scale dashboard control: it must stay small and
     unobtrusive at every Display Size setting, not grow to 300% with the
     tiles. It's also a normal flex-flow item (not position:fixed), so it
     always reserves its own space and can never end up overlapped by or
     hidden behind scaled dashboard content. */
  .app-footer {
    flex-shrink: 0;
    border-top: 1px solid var(--border-color);
    background: var(--bg-app);
    padding: 4px 16px;
    text-align: center;
  }

  .line {
    display: inline-block;
    max-width: 100%;
    font-size: 11px;
    line-height: 1.5;
    color: var(--text-secondary);
    font-variant-numeric: tabular-nums;
  }
</style>
