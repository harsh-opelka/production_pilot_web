<script>
  // Service-level only (see Sidebar.svelte, the only place that links
  // here) — Management never sees this page or its controls.
  import { lang, theme, uiScale } from './stores.js';
  import { translate } from './translations.js';
  import ViewToggle from './ViewToggle.svelte';

  function toggleLang() {
    lang.set($lang === 'en' ? 'de' : 'en');
  }

  function toggleTheme() {
    theme.set($theme === 'dark' ? 'light' : 'dark');
  }

  const SCALE_MIN = 0.7;
  const SCALE_MAX = 3.0;
  const SCALE_STEP = 0.05;

  // Dragging the slider used to call uiScale.set() on every 'input'
  // event (every pixel of movement), which both rewrote localStorage
  // and pushed a new --ui-scale onto <html> each time — since root
  // font-size is calc(100% * var(--ui-scale)), that's a full-page
  // relayout per pixel, which is what caused the dashboard to flicker
  // while dragging. Fix: 'input' only updates this local dragValue (for
  // the live percentage label + thumb position); the store — and so
  // the actual --ui-scale/localStorage write — only commits on
  // 'change' (release, or a keyboard step, which fires input+change
  // together). The +/- buttons below commit straight to the store
  // too, since a single click is already a single relayout.
  let dragValue = $state($uiScale);

  $effect(() => {
    dragValue = $uiScale;
  });

  function onScaleInput(event) {
    dragValue = Number(event.target.value);
  }

  function onScaleChange(event) {
    uiScale.set(Number(event.target.value));
  }

  function clampScale(value) {
    return Math.min(SCALE_MAX, Math.max(SCALE_MIN, Math.round(value * 100) / 100));
  }

  function stepScale(delta) {
    uiScale.set(clampScale($uiScale + delta));
  }
</script>

<div class="settings">
  <h1>{translate($lang, 'nav_settings')}</h1>

  <div class="row">
    <span class="label">{translate($lang, 'settings_language')}</span>
    <button class="toggle" onclick={toggleLang} aria-label="Toggle language">
      <span class:dim={$lang !== 'en'}>EN</span>
      <span class="sep">/</span>
      <span class:dim={$lang !== 'de'}>DE</span>
    </button>
  </div>

  <div class="row">
    <span class="label">{translate($lang, 'settings_theme')}</span>
    <button class="toggle" onclick={toggleTheme} aria-label="Toggle theme">
      {translate($lang, $theme === 'dark' ? 'theme_dark' : 'theme_light')}
    </button>
  </div>

  <div class="row">
    <span class="label">{translate($lang, 'display_size')}</span>
    <div class="scale-row">
      <button
        type="button"
        class="scale-step"
        onclick={() => stepScale(-SCALE_STEP)}
        disabled={$uiScale <= SCALE_MIN}
        aria-label="Decrease display size"
      >
        −
      </button>
      <input
        id="ui-scale-slider"
        type="range"
        min={SCALE_MIN}
        max={SCALE_MAX}
        step={SCALE_STEP}
        value={dragValue}
        oninput={onScaleInput}
        onchange={onScaleChange}
        aria-valuetext="{Math.round(dragValue * 100)}%"
      />
      <button
        type="button"
        class="scale-step"
        onclick={() => stepScale(SCALE_STEP)}
        disabled={$uiScale >= SCALE_MAX}
        aria-label="Increase display size"
      >
        +
      </button>
      <span class="scale-value">{Math.round(dragValue * 100)}%</span>
    </div>
  </div>

  <div class="row">
    <span class="label">{translate($lang, 'settings_view')}</span>
    <ViewToggle />
  </div>
</div>

<style>
  .settings {
    height: 100%;
    overflow-y: auto;
    padding: clamp(0.75rem, 1.5vh, 1.5rem) clamp(1rem, 2vw, 2rem);
    display: flex;
    flex-direction: column;
    gap: clamp(1rem, 2vh, 1.5rem);
    max-width: 32rem;
  }

  h1 {
    margin: 0;
    font-size: var(--font-group-header);
    color: var(--text-primary);
  }

  .row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: clamp(0.75rem, 1.5vw, 1.5rem);
    padding: clamp(0.6rem, 1.2vh, 1rem);
    background: var(--bg-panel);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
  }

  .label {
    font-size: var(--font-toggle);
    color: var(--text-secondary);
  }

  /* Matches ViewToggle's ("Dashboard View") style — was previously
     --sidebar-active-bg (a fixed dark navy, left over from when this
     button lived in the always-dark Sidebar) + --text-primary, which in
     Light theme is dark-on-dark and unreadable. --opelka-blue/-fg are
     theme-independent, so this reads correctly in both themes. */
  .toggle {
    background: var(--opelka-blue);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    color: var(--opelka-blue-fg);
    font-weight: 600;
    font-size: var(--font-toggle);
    padding: clamp(0.5rem, 1vh, 0.8rem) clamp(0.9rem, 1.4vw, 1.25rem);
  }

  .toggle .dim {
    opacity: 0.4;
  }

  .toggle .sep {
    opacity: 0.4;
    margin: 0 0.2em;
  }

  .scale-row {
    display: flex;
    align-items: center;
    gap: clamp(0.5rem, 0.8vw, 0.75rem);
  }

  .scale-row input[type='range'] {
    flex: 1;
    min-width: 0;
    accent-color: var(--opelka-blue);
  }

  .scale-step {
    flex: 0 0 auto;
    width: clamp(1.6rem, 2.2vw, 2rem);
    height: clamp(1.6rem, 2.2vw, 2rem);
    display: flex;
    align-items: center;
    justify-content: center;
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    background: var(--bg-app);
    color: var(--text-primary);
    font-size: var(--font-toggle);
    font-weight: 700;
    line-height: 1;
    padding: 0;
  }

  .scale-step:disabled {
    opacity: 0.4;
    cursor: default;
  }

  .scale-value {
    font-size: var(--font-toggle);
    color: var(--text-primary);
    min-width: 3.5ch;
    text-align: right;
    font-variant-numeric: tabular-nums;
  }
</style>
