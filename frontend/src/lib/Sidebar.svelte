<script>
  import { page, lang, auth } from './stores.js';
  import { translate } from './translations.js';
  import { logout } from './serviceApi.js';
</script>

<nav class="sidebar">
  <ul class="nav">
    <li>
      <button class:active={$page === 'dashboard'} onclick={() => page.set('dashboard')}>
        {translate($lang, 'nav_dashboard')}
      </button>
    </li>
    <li>
      <button class:active={$page === 'statistics'} onclick={() => page.set('statistics')}>
        {translate($lang, 'nav_statistics')}
      </button>
    </li>
    {#if $auth.level === 'service'}
      <li>
        <button class:active={$page === 'service'} onclick={() => page.set('service')}>
          {translate($lang, 'nav_service')}
        </button>
      </li>
      <li>
        <button class:active={$page === 'settings'} onclick={() => page.set('settings')}>
          {translate($lang, 'nav_settings')}
        </button>
      </li>
    {/if}
  </ul>

  <div class="bottom">
    <button class="toggle" onclick={logout}>
      {translate($lang, 'logout')}
    </button>
  </div>
</nav>

<style>
  .sidebar {
    width: clamp(11rem, 14vw, 15.5rem);
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
    line-height: 1.2;
    padding: clamp(0.6rem, 1.2vh, 1rem) clamp(0.65rem, 1vw, 0.95rem);
    /* Buttons default to white-space:pre in Chromium/Firefox, which is
       what was actually clipping "Einstellungen" instead of letting it
       wrap — the fixed sidebar width alone was never the whole story.
       Normal wrapping is the fallback if a label ever doesn't fit the
       widened sidebar + trimmed font-size above. */
    white-space: normal;
    overflow-wrap: break-word;
  }

  .nav button.active {
    background: var(--sidebar-active-bg);
    color: var(--sidebar-fg);
    font-weight: 600;
    box-shadow: inset 3px 0 0 var(--sidebar-accent);
  }

  .bottom {
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
</style>
