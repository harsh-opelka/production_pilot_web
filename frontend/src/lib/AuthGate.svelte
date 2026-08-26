<script>
  import { auth, lang } from './stores.js';
  import { translate } from './translations.js';
  import { login, ServiceApiError } from './serviceApi.js';

  let open = $state(false);
  let password = $state('');
  let error = $state('');
  let loading = $state(false);
  let passwordInput;

  function openGate() {
    open = true;
    error = '';
    password = '';
  }

  function closeGate() {
    open = false;
    error = '';
    password = '';
  }

  async function submit(event) {
    event.preventDefault();
    if (loading || !password) return;
    error = '';
    loading = true;
    try {
      await login(password);
      // Success — $auth.token becomes truthy, App.svelte renders the
      // sidebar; this component reacts to that itself (see {#if} below).
      password = '';
      open = false;
    } catch (err) {
      error =
        err instanceof ServiceApiError && err.status === 429
          ? translate($lang, 'service_too_many_attempts')
          : translate($lang, 'auth_gate_incorrect');
    } finally {
      loading = false;
    }
  }

  $effect(() => {
    if (open) passwordInput?.focus();
  });
</script>

{#if !$auth.token}
  <button
    type="button"
    class="gear-button"
    onclick={openGate}
    aria-label={translate($lang, 'gear_tooltip')}
    title={translate($lang, 'gear_tooltip')}
  >
    ⚙
  </button>
{/if}

{#if open}
  <div class="overlay" onclick={closeGate} role="presentation">
    <form class="card" onsubmit={submit} onclick={(e) => e.stopPropagation()}>
      <button type="button" class="close" onclick={closeGate} aria-label={translate($lang, 'close')}>×</button>
      <h2>{translate($lang, 'auth_gate_title')}</h2>

      <label class="field">
        <span>{translate($lang, 'auth_gate_prompt')}</span>
        <input type="password" bind:value={password} bind:this={passwordInput} />
      </label>

      {#if error}
        <p class="error">{error}</p>
      {/if}

      <button type="submit" disabled={loading || !password}>{translate($lang, 'unlock')}</button>
    </form>
  </div>
{/if}

<style>
  /* A normal flex item inside .topbar (see TopBar.svelte) — flex:0 0
     auto, so it just takes its own small size at the start of the row
     without disturbing the next-action/logo layout or its wrap
     behavior at high --ui-scale. */
  .gear-button {
    flex: 0 0 auto;
    width: 2.25rem;
    height: 2.25rem;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    border: 1px solid var(--border-color);
    background: var(--bg-panel);
    color: var(--text-secondary);
    font-size: 1.2rem;
    line-height: 1;
  }

  .gear-button:hover {
    color: var(--text-primary);
  }

  /* The overlay itself is position:fixed, so being a flex child of
     .topbar (normal document flow) doesn't affect it — it still covers
     the full viewport regardless of where in the DOM it's mounted. */
  .overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 100;
  }

  .card {
    position: relative;
    background: var(--bg-panel);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    padding: clamp(1.5rem, 3vh, 2.5rem);
    width: min(90vw, 420px);
    display: flex;
    flex-direction: column;
    gap: clamp(0.75rem, 1.5vh, 1.25rem);
  }

  .close {
    position: absolute;
    top: 0.5rem;
    right: 0.5rem;
    background: transparent;
    border: none;
    font-size: 1.5rem;
    line-height: 1;
    color: var(--text-secondary);
    padding: 0.25rem;
  }

  h2 {
    margin: 0;
    font-size: var(--font-group-header);
    color: var(--text-primary);
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
    font-size: var(--font-toggle);
    color: var(--text-secondary);
  }

  input {
    font-size: var(--font-toggle);
    padding: clamp(0.5rem, 1vh, 0.75rem);
    border-radius: var(--radius);
    border: 1px solid var(--border-color);
    background: var(--bg-app);
    color: var(--text-primary);
  }

  .error {
    margin: 0;
    color: var(--danger-bg);
    font-size: var(--font-toggle);
    font-weight: 600;
  }

  button[type='submit'] {
    font-size: var(--font-toggle);
    font-weight: 600;
    padding: clamp(0.6rem, 1.1vh, 0.9rem);
    border: none;
    border-radius: var(--radius);
    background: var(--accent);
    color: var(--opelka-blue-fg);
  }

  button[type='submit']:disabled {
    opacity: 0.5;
    cursor: default;
  }
</style>
