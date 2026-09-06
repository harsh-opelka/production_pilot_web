<script>
  import logo from '../assets/opelka_logo.png';
  import { machinesState, lang, page } from './stores.js';
  import { translate } from './translations.js';
  import { computeNextAction } from './nextAction.js';
  import AuthGate from './AuthGate.svelte';
  import KpiSummary from './KpiSummary.svelte';

  let nextAction = $derived(computeNextAction($machinesState.groups, $lang));
</script>

<header class="topbar">
  <AuthGate />

  <div class="next-action">
    <div class="next-action-box tier-{nextAction.tier}">
      <span class="na-label">{translate($lang, 'next_action_prefix')}</span>
      <span class="na-content">{nextAction.text}</span>
    </div>
  </div>

  {#if $page === 'dashboard'}
    <KpiSummary />
  {/if}

  <div class="logo-panel">
    <img src={logo} alt="Opelka" />
  </div>
</header>

<style>
  .topbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    background: var(--bg-topbar);
    border-bottom: 1px solid var(--border-color);
    padding: clamp(0.5rem, 1.2vh, 1rem) clamp(1rem, 2vw, 2rem);
    gap: clamp(0.5rem, 1vh, 1rem) clamp(0.75rem, 1.5vw, 1.5rem);
    flex-shrink: 0;
  }

  /* flex-basis 16rem (not 0) makes this wrap onto its own full-width row
     at high --ui-scale instead of being squeezed to a sliver next to the
     non-shrinking logo. */
  .next-action {
    flex: 1 1 16rem;
    min-width: 0;
    display: flex;
  }

  /* Two-tier hierarchy inside one coloured box: a small label on top
     (na-label) and the combined "{unit}: action" text below it in a much
     larger, bold weight (na-content) — see nextAction.js for how that
     text is built. The tier-* background colours below are unchanged
     from the previous single-line pill. */
  .next-action-box {
    flex: 1 1 auto;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: clamp(0.05rem, 0.2vh, 0.2rem);
    padding: clamp(0.3rem, 0.7vh, 0.55rem) clamp(0.7rem, 1.3vw, 1.1rem);
    border-radius: var(--radius);
    color: #ffffff;
  }

  .na-label {
    font-size: calc(var(--font-next-action) * 0.42);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    opacity: 0.85;
  }

  .na-content {
    font-size: var(--font-next-action);
    font-weight: 700;
    line-height: 1.15;
    overflow-wrap: break-word;
  }

  .tier-error {
    background: var(--state-error);
  }

  .tier-baking {
    background: var(--tier-baking-bg);
  }

  .tier-ready {
    background: var(--opelka-blue);
  }

  .tier-none {
    background: var(--tier-none-bg);
  }

  .logo-panel {
    flex: 0 0 auto;
    background: var(--logo-panel-bg);
    border-radius: var(--radius);
    padding: clamp(0.3rem, 0.6vh, 0.6rem) clamp(0.6rem, 1vw, 1rem);
    display: inline-flex;
  }

  .logo-panel img {
    height: clamp(1.75rem, 4vh, 3.25rem);
    width: auto;
  }
</style>
