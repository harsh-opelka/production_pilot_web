<script>
  // Service setting: the New Cycle start delay — after a machine is started
  // at the beginning of a new cycle, the next machine is only asked for
  // once this many seconds have passed (backend production_pilot/
  // new_cycle.py). GET/PUT /api/service/new-cycle-delay. A changed value
  // applies to the next delay; a countdown already running keeps its value.
  //
  // Also shows each group's live new_cycle flag / countdown — technical
  // detail, and this card is only reachable at Service level.
  import { onMount } from 'svelte';
  import { lang, machinesState, nowTick } from './stores.js';
  import { translate } from './translations.js';
  import { formatCountdown } from './format.js';
  import { getNewCycleDelay, setNewCycleDelay, ServiceApiError } from './serviceApi.js';

  let delay = $state('');
  let min = $state(10);
  let max = $state(3600);
  let saving = $state(false);
  let error = $state('');
  let success = $state('');

  onMount(async () => {
    try {
      const data = await getNewCycleDelay();
      delay = data.delay_seconds;
      min = data.min_seconds;
      max = data.max_seconds;
    } catch (err) {
      error = err instanceof ServiceApiError ? err.message : String(err);
    }
  });

  async function submit(event) {
    event.preventDefault();
    error = '';
    success = '';
    const value = Number(delay);
    if (delay === '' || !Number.isInteger(value) || value < min || value > max) {
      error = translate($lang, 'service_new_cycle_invalid', { min, max });
      return;
    }
    saving = true;
    try {
      const result = await setNewCycleDelay(value);
      delay = result.delay_seconds;
      success = translate($lang, 'service_new_cycle_saved');
    } catch (err) {
      error = err instanceof ServiceApiError ? err.message : String(err);
    } finally {
      saving = false;
    }
  }

  let elapsed = $derived($machinesState.received_at ? ($nowTick - $machinesState.received_at) / 1000 : 0);
</script>

<h2>{translate($lang, 'service_new_cycle_heading')}</h2>
<p class="help">{translate($lang, 'service_new_cycle_help')}</p>
<form onsubmit={submit}>
  <label class="field">
    <span>{translate($lang, 'service_new_cycle_label')}</span>
    <span class="input-row">
      <input type="number" {min} {max} step="1" bind:value={delay} />
      <span class="unit">{translate($lang, 'service_new_cycle_unit')}</span>
    </span>
  </label>

  {#if error}
    <p class="error">{error}</p>
  {/if}
  {#if success}
    <p class="success">{success}</p>
  {/if}

  <button type="submit" disabled={saving}>{translate($lang, 'service_save')}</button>
</form>

{#if $machinesState.groups?.length}
  <div class="status">
    <span class="status-title">{translate($lang, 'service_new_cycle_status')}</span>
    {#each $machinesState.groups as group (group.name)}
      <span class="status-row">
        <span class="group">{group.name}:</span>
        {translate($lang, group.new_cycle ? 'service_new_cycle_on' : 'service_new_cycle_off')}
        {#if group.wait_remaining_seconds}
          · {translate($lang, 'service_new_cycle_waiting', {
            time: formatCountdown(Math.max(0, group.wait_remaining_seconds - Math.floor(elapsed))),
          })}
        {/if}
      </span>
    {/each}
  </div>
{/if}

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

  .input-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
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

  .unit {
    color: var(--text-secondary);
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

  .status {
    margin-top: clamp(0.75rem, 1.5vh, 1.25rem);
    padding-top: 0.6rem;
    border-top: 1px solid var(--border-color);
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    font-size: var(--font-tile-sub);
    color: var(--text-secondary);
  }

  .status-title {
    font-weight: 600;
  }

  .group {
    color: var(--text-primary);
    font-weight: 600;
  }
</style>
