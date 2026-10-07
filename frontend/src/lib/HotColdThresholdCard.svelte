<script>
  // Service-only card (see ServiceHome.svelte's "Data" section). The oil
  // temperature at which a Standby machine counts as Hot rather than Cold —
  // applied by the backend's poll loop (production_pilot/hot_cold.py) from
  // the next poll on. GET/PUT /api/service/hot-cold-threshold.
  import { onMount } from 'svelte';
  import { lang } from './stores.js';
  import { translate } from './translations.js';
  import { getHotColdThreshold, setHotColdThreshold, ServiceApiError } from './serviceApi.js';

  const MIN_C = 20;
  const MAX_C = 150;

  let threshold = $state(50);
  let error = $state('');
  let success = $state('');
  let saving = $state(false);

  onMount(async () => {
    try {
      const data = await getHotColdThreshold();
      threshold = data.threshold_c;
    } catch (err) {
      error = err instanceof ServiceApiError ? err.message : String(err);
    }
  });

  async function submit(event) {
    event.preventDefault();
    error = '';
    success = '';
    const value = Number(threshold);
    if (threshold === '' || threshold == null || !Number.isFinite(value) || value < MIN_C || value > MAX_C) {
      error = translate($lang, 'service_hot_cold_invalid');
      return;
    }
    saving = true;
    try {
      const result = await setHotColdThreshold(value);
      threshold = result.threshold_c;
      success = translate($lang, 'service_hot_cold_saved');
    } catch (err) {
      error = err instanceof ServiceApiError ? err.message : String(err);
    } finally {
      saving = false;
    }
  }
</script>

<h2>{translate($lang, 'service_hot_cold_heading')}</h2>
<p class="help">{translate($lang, 'service_hot_cold_help')}</p>
<form onsubmit={submit}>
  <label class="field">
    <span>{translate($lang, 'service_hot_cold_label')}</span>
    <input type="number" min={MIN_C} max={MAX_C} step="any" bind:value={threshold} />
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

  .help {
    margin: 0 0 clamp(0.65rem, 1.2vh, 1rem);
    color: var(--text-secondary);
    font-size: var(--font-toggle);
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
    max-width: 8rem;
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
