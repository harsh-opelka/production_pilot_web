<script>
  import logo from '../assets/opelka_logo.png';
  import { machinesState, lang } from './stores.js';
  import { translate } from './translations.js';
  import { computeNextAction } from './nextAction.js';

  let nextActionText = $derived(computeNextAction($machinesState.groups, $lang));
</script>

<header class="topbar">
  <div class="title">Produktionspilot</div>

  <div class="next-action">
    <span class="prefix">{translate($lang, 'next_action_prefix')}</span>
    <span class="value">{nextActionText}</span>
  </div>

  <div class="logo-panel">
    <img src={logo} alt="Opelka" />
  </div>
</header>

<style>
  .topbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    background: var(--bg-topbar);
    border-bottom: 1px solid var(--border-color);
    padding: clamp(0.5rem, 1.2vh, 1rem) clamp(1rem, 2vw, 2rem);
    gap: clamp(0.5rem, 1vh, 1rem) clamp(0.75rem, 1.5vw, 1.5rem);
    flex-shrink: 0;
  }

  .title {
    flex: 0 0 auto;
    font-size: var(--font-app-title);
    font-weight: 700;
    color: var(--text-primary);
    white-space: nowrap;
  }

  /* flex-basis 16rem (not 0) makes this wrap onto its own full-width row
     at high --ui-scale instead of being squeezed to a sliver between the
     non-shrinking title and logo. */
  .next-action {
    flex: 1 1 16rem;
    min-width: 0;
    text-align: center;
    font-size: var(--font-next-action);
    font-weight: 700;
    color: var(--accent);
  }

  .next-action .prefix {
    opacity: 0.75;
    margin-right: 0.4em;
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
