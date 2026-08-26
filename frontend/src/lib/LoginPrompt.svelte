<script>
  import { onMount } from 'svelte';
  import { lang, serviceSessionExpired } from './stores.js';
  import { translate } from './translations.js';
  import { login, ServiceApiError } from './serviceApi.js';

  let password = $state('');
  let error = $state('');
  let loading = $state(false);
  let passwordInput;

  onMount(() => passwordInput?.focus());

  async function submit(event) {
    event.preventDefault();
    if (loading || !password) return;
    serviceSessionExpired.set(false);
    error = '';
    loading = true;
    try {
      await login(password);
      password = '';
    } catch (err) {
      error =
        err instanceof ServiceApiError && err.status === 429
          ? translate($lang, 'service_too_many_attempts')
          : translate($lang, 'service_password_incorrect');
    } finally {
      loading = false;
    }
  }
</script>

<div class="gate">
  <form class="card" onsubmit={submit}>
    <h2>{translate($lang, 'service_password_title')}</h2>

    {#if $serviceSessionExpired}
      <p class="notice">{translate($lang, 'service_session_expired')}</p>
    {/if}

    <label class="field">
      <span>{translate($lang, 'service_password_prompt')}</span>
      <input type="password" bind:value={password} bind:this={passwordInput} />
    </label>

    {#if error}
      <p class="error">{error}</p>
    {/if}

    <button type="submit" disabled={loading || !password}>{translate($lang, 'unlock')}</button>
  </form>
</div>

<style>
  .gate {
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .card {
    background: var(--bg-panel);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    padding: clamp(1.5rem, 3vh, 2.5rem);
    width: min(90vw, 420px);
    display: flex;
    flex-direction: column;
    gap: clamp(0.75rem, 1.5vh, 1.25rem);
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

  /* A pill, not bare coloured text: --accent is now a dark brand blue, so
     plain text in that colour would be nearly unreadable directly on the
     (also dark) panel background in dark theme — same fix as the tier
     pills in TopBar. */
  .notice {
    margin: 0;
    display: inline-block;
    background: var(--accent);
    color: var(--opelka-blue-fg);
    padding: 0.3em 0.6em;
    border-radius: var(--radius);
    font-size: var(--font-toggle);
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
