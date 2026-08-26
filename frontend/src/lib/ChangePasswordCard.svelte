<script>
  import { lang } from './stores.js';
  import { translate } from './translations.js';
  import { changePassword, ServiceApiError } from './serviceApi.js';

  let current = $state('');
  let next = $state('');
  let confirm = $state('');
  let error = $state('');
  let success = $state('');
  let saving = $state(false);

  async function submit(event) {
    event.preventDefault();
    error = '';
    success = '';

    if (!next) {
      error = translate($lang, 'service_password_empty');
      return;
    }
    if (next !== confirm) {
      error = translate($lang, 'service_password_mismatch');
      return;
    }

    saving = true;
    try {
      await changePassword(current, next);
      success = translate($lang, 'service_password_updated');
      current = '';
      next = '';
      confirm = '';
    } catch (err) {
      error =
        err instanceof ServiceApiError && err.status === 401
          ? translate($lang, 'service_password_current_incorrect')
          : err.message;
    } finally {
      saving = false;
    }
  }
</script>

<h2>{translate($lang, 'service_change_password')}</h2>
<form onsubmit={submit}>
  <label class="field">
    <span>{translate($lang, 'service_current_password')}</span>
    <input type="password" bind:value={current} />
  </label>
  <label class="field">
    <span>{translate($lang, 'service_new_password')}</span>
    <input type="password" bind:value={next} />
  </label>
  <label class="field">
    <span>{translate($lang, 'service_confirm_password')}</span>
    <input type="password" bind:value={confirm} />
  </label>

  {#if error}
    <p class="error">{error}</p>
  {/if}
  {#if success}
    <p class="success">{success}</p>
  {/if}

  <button type="submit" disabled={saving}>{translate($lang, 'service_save')}</button>
</form>

<style>
  h2 {
    margin: 0 0 clamp(0.75rem, 1.5vh, 1.25rem);
    font-size: var(--font-group-header);
    color: var(--text-primary);
  }

  form {
    display: flex;
    flex-direction: column;
    gap: clamp(0.65rem, 1.2vh, 1rem);
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
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

  .success {
    margin: 0;
    color: var(--state-baking);
    font-size: var(--font-toggle);
    font-weight: 600;
  }

  button[type='submit'] {
    align-self: flex-start;
    font-size: var(--font-toggle);
    font-weight: 600;
    padding: clamp(0.5rem, 1vh, 0.75rem) clamp(1.1rem, 2vw, 1.75rem);
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
