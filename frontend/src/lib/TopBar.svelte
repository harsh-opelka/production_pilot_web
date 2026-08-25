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
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: center;
    background: var(--bg-topbar);
    border-bottom: 1px solid var(--border-color);
    padding: clamp(0.5rem, 1.2vh, 1rem) clamp(1rem, 2vw, 2rem);
    gap: clamp(0.75rem, 1.5vw, 1.5rem);
    flex-shrink: 0;
  }

  .title {
    font-size: var(--font-app-title);
    font-weight: 700;
    color: var(--text-primary);
    white-space: nowrap;
  }

  .next-action {
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
    background: var(--logo-panel-bg);
    border-radius: var(--radius);
    padding: clamp(0.3rem, 0.6vh, 0.6rem) clamp(0.6rem, 1vw, 1rem);
    display: inline-flex;
    flex-shrink: 0;
  }

  .logo-panel img {
    height: clamp(1.75rem, 4vh, 3.25rem);
    width: auto;
  }
</style>
