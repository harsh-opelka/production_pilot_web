<script>
  import { page, lang, theme, uiScale } from './stores.js';
  import { translate } from './translations.js';

  function toggleLang() {
    lang.set($lang === 'en' ? 'de' : 'en');
  }

  function toggleTheme() {
    theme.set($theme === 'dark' ? 'light' : 'dark');
  }

  function onScaleInput(event) {
    uiScale.set(Number(event.target.value));
  }
</script>

<nav class="sidebar">
  <ul class="nav">
    <li>
      <button class:active={$page === 'dashboard'} onclick={() => page.set('dashboard')}>
        {translate($lang, 'nav_dashboard')}
      </button>
    </li>
    <li>
      <button class:active={$page === 'service'} onclick={() => page.set('service')}>
        {translate($lang, 'nav_service')}
      </button>
    </li>
  </ul>

  <div class="toggles">
    <button class="toggle" onclick={toggleLang} aria-label="Toggle language">
      <span class:dim={$lang !== 'en'}>EN</span>
      <span class="sep">/</span>
      <span class:dim={$lang !== 'de'}>DE</span>
    </button>
    <button class="toggle" onclick={toggleTheme} aria-label="Toggle theme">
      {translate($lang, $theme === 'dark' ? 'theme_dark' : 'theme_light')}
    </button>

    <div class="scale-control">
      <label class="scale-label" for="ui-scale-slider">{translate($lang, 'display_size')}</label>
      <div class="scale-row">
        <input
          id="ui-scale-slider"
          type="range"
          min="0.7"
          max="1.5"
          step="0.05"
          value={$uiScale}
          oninput={onScaleInput}
          aria-valuetext="{Math.round($uiScale * 100)}%"
        />
        <span class="scale-value">{Math.round($uiScale * 100)}%</span>
      </div>
    </div>
  </div>
</nav>

<style>
  .sidebar {
    width: clamp(10rem, 12vw, 13.75rem);
    flex-shrink: 0;
    height: 100%;
    background: var(--sidebar-bg);
    color: var(--sidebar-fg);
    display: flex;
    flex-direction: column;
    padding: clamp(1rem, 2vh, 1.75rem) clamp(0.5rem, 1vw, 1rem);
  }

  .nav {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: clamp(0.4rem, 0.8vh, 0.75rem);
  }

  .nav button {
    width: 100%;
    text-align: left;
    background: transparent;
    border: none;
    border-radius: var(--radius);
    color: var(--sidebar-fg-muted);
    font-size: var(--font-nav-item);
    padding: clamp(0.6rem, 1.2vh, 1rem) clamp(0.75rem, 1.2vw, 1.1rem);
  }

  .nav button.active {
    background: var(--sidebar-active-bg);
    color: var(--sidebar-fg);
    font-weight: 600;
    box-shadow: inset 3px 0 0 var(--sidebar-accent);
  }

  .toggles {
    margin-top: auto;
    display: flex;
    flex-direction: column;
    gap: clamp(0.4rem, 0.8vh, 0.6rem);
  }

  .toggle {
    background: var(--sidebar-active-bg);
    border: none;
    border-radius: var(--radius);
    color: var(--sidebar-fg);
    font-size: var(--font-toggle);
    padding: clamp(0.5rem, 1vh, 0.8rem);
  }

  .toggle .dim {
    opacity: 0.4;
  }

  .toggle .sep {
    opacity: 0.4;
    margin: 0 0.2em;
  }

  .scale-control {
    margin-top: clamp(0.3rem, 0.6vh, 0.5rem);
    display: flex;
    flex-direction: column;
    gap: clamp(0.3rem, 0.5vh, 0.45rem);
  }

  .scale-label {
    font-size: var(--font-toggle);
    color: var(--sidebar-fg-muted);
  }

  .scale-row {
    display: flex;
    align-items: center;
    gap: clamp(0.5rem, 0.8vw, 0.75rem);
  }

  .scale-row input[type='range'] {
    flex: 1;
    min-width: 0;
    accent-color: var(--sidebar-accent);
  }

  .scale-value {
    font-size: var(--font-toggle);
    color: var(--sidebar-fg);
    min-width: 3.5ch;
    text-align: right;
    font-variant-numeric: tabular-nums;
    flex-shrink: 0;
  }
</style>
