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
    <span class="prefix">{translate($lang, 'next_action_prefix')}</span>
    <span class="pill tier-{nextAction.tier}">{nextAction.text}</span>
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
     non-shrinking logo. Its own children (label, pill) wrap onto separate
     lines too if they don't both fit — see .pill below. */
  .next-action {
    flex: 1 1 16rem;
    min-width: 0;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: clamp(0.4rem, 0.8vw, 0.75rem);
  }

  .prefix {
    flex: 0 0 auto;
    font-size: var(--font-next-action);
    font-weight: 700;
    color: var(--text-primary);
  }

  .pill {
    flex: 1 1 auto;
    min-width: 0;
    overflow-wrap: break-word;
    font-size: var(--font-next-action);
    font-weight: 700;
    color: #ffffff;
    padding: clamp(0.15rem, 0.4vh, 0.35rem) clamp(0.6rem, 1.2vw, 1rem);
    border-radius: var(--radius);
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
