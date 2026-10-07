<script>
  // While a demo is being recorded and the user is on a page without the
  // Demo button (Statistics, Service, Settings), a small red "● REC 00:42"
  // chip in the corner keeps it obvious — click it to stop and save.
  import { lang, nowTick, page } from './stores.js';
  import { translate } from './translations.js';
  import { formatClock } from './demoMode.js';
  import { recorder, stopRecording } from './demoRecorder.js';

  let time = $derived($recorder.startedAt ? formatClock(($nowTick - $recorder.startedAt) / 1000) : '');
</script>

{#if $recorder.phase === 'recording' && $page !== 'dashboard'}
  <button type="button" class="rec-chip" title={translate($lang, 'demo_stop')} onclick={() => stopRecording('user')}>
    <span class="dot" aria-hidden="true"></span>
    {translate($lang, 'demo_rec')} {time} · {translate($lang, 'demo_stop')}
  </button>
{/if}

<style>
  .rec-chip {
    position: fixed;
    right: 1rem;
    bottom: 2.5rem;
    z-index: 1500;
    display: inline-flex;
    align-items: center;
    gap: 0.45em;
    padding: 0.35rem 0.8rem;
    font: inherit;
    font-size: 0.85rem;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    color: #ffffff;
    background: var(--danger-bg);
    border: none;
    border-radius: 999px;
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.3);
    cursor: pointer;
  }

  .dot {
    width: 0.6em;
    height: 0.6em;
    border-radius: 50%;
    background: #ffffff;
    animation: pulse 1.2s ease-in-out infinite;
  }

  @keyframes pulse {
    50% {
      opacity: 0.25;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .dot {
      animation: none;
    }
  }
</style>
