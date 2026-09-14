<script>
  // Service-only. Wraps /api/service/data-source (real/demo switch) and,
  // while in demo mode, /api/service/demo/state + /api/service/demo/set-state
  // (the control panel below). Everything downstream of the switch — the
  // poll loop, priority calc, history, WS broadcast, KPI endpoints — is
  // unaware this exists; this card is the only place demo mode surfaces
  // in the UI (see server.py's _poll_loop for the backend equivalent).
  import { onMount } from 'svelte';
  import { lang } from './stores.js';
  import { translate } from './translations.js';
  import {
    getDataSource,
    setDataSource,
    getDemoState,
    setDemoPlcState,
    ServiceApiError,
  } from './serviceApi.js';

  const STATES = ['COLD', 'HEATING', 'READY', 'BAKING', 'ERROR'];
  const STATE_KEY = {
    COLD: 'state_cold',
    HEATING: 'state_heating',
    READY: 'state_ready',
    BAKING: 'state_baking',
    ERROR: 'state_error',
  };

  // Fixed list for now — mirrors production_pilot/demo_source.py's
  // RECIPE_OPTIONS. Product names, not UI copy, so they're shown as-is
  // in every language rather than run through translate().
  const RECIPES = ['Quarkballs', 'Berliners', 'Donuts', 'Apfelschnenken'];

  let mode = $state('real');
  let groups = $state([]); // [{name, type, plcs:[{ip, unit_number, state, is_online, remaining_seconds}]}]
  let error = $state('');
  let loading = $state(true);
  let switching = $state(false);

  async function refreshMode() {
    const status = await getDataSource();
    mode = status.mode;
  }

  async function refreshDemoState() {
    if (mode !== 'demo') {
      groups = [];
      return;
    }
    const state = await getDemoState();
    groups = state.groups;
  }

  onMount(async () => {
    try {
      await refreshMode();
      await refreshDemoState();
    } catch (err) {
      error = err instanceof ServiceApiError ? err.message : String(err);
    } finally {
      loading = false;
    }
  });

  async function selectMode(next) {
    if (next === mode || switching) return;
    error = '';
    switching = true;
    try {
      await setDataSource(next);
      mode = next;
      await refreshDemoState();
    } catch (err) {
      error =
        err instanceof ServiceApiError
          ? translate($lang, 'service_data_source_error', { error: err.message })
          : String(err);
    } finally {
      switching = false;
    }
  }

  async function updatePlc(groupName, ip, changes) {
    error = '';
    try {
      const state = await setDemoPlcState(groupName, ip, changes);
      groups = state.groups;
    } catch (err) {
      error =
        err instanceof ServiceApiError
          ? translate($lang, 'service_demo_error', { error: err.message })
          : String(err);
    }
  }

  function onStateChange(groupName, ip, value) {
    updatePlc(groupName, ip, { state: value });
  }

  function onOnlineChange(groupName, ip, checked) {
    updatePlc(groupName, ip, { is_online: checked });
  }

  function onRemainingChange(groupName, ip, value) {
    const seconds = Math.round(Number(value));
    if (!Number.isFinite(seconds) || seconds < 0) return;
    updatePlc(groupName, ip, { remaining_seconds: seconds });
  }

  function onRecipeChange(groupName, ip, value) {
    // value is '' for the blank/"None" option — set_plc_state treats an
    // explicit empty string as "clear it" (see its docstring), distinct
    // from omitting the field entirely.
    updatePlc(groupName, ip, { recipe: value });
  }
</script>

<h2>{translate($lang, 'service_data_source_heading')}</h2>

<div class="mode-toggle" role="radiogroup" aria-label={translate($lang, 'service_data_source_heading')}>
  <button
    type="button"
    class:active={mode === 'real'}
    disabled={loading || switching}
    onclick={() => selectMode('real')}
  >
    {translate($lang, 'service_data_source_real')}
  </button>
  <button
    type="button"
    class:active={mode === 'demo'}
    disabled={loading || switching}
    onclick={() => selectMode('demo')}
  >
    {translate($lang, 'service_data_source_demo')}
  </button>
</div>

{#if error}
  <p class="error">{error}</p>
{/if}

{#if mode === 'demo'}
  <div class="demo-controls">
    <h3>{translate($lang, 'service_demo_controls_heading')}</h3>
    {#each groups as group (group.name)}
      <div class="demo-group">
        <p class="demo-group-name">{group.name} <span class="demo-group-type">({group.type})</span></p>
        <div class="demo-table">
          <div class="demo-row demo-row-head">
            <span>{translate($lang, 'service_demo_unit_col')}</span>
            <span>{translate($lang, 'service_demo_state_col')}</span>
            <span>{translate($lang, 'service_demo_recipe_col')}</span>
            <span>{translate($lang, 'service_demo_online_col')}</span>
            <span>{translate($lang, 'service_demo_remaining_col')}</span>
          </div>
          {#each group.plcs as plc (plc.ip)}
            <div class="demo-row">
              <span class="demo-unit">{plc.unit_number}</span>
              <select value={plc.state} onchange={(e) => onStateChange(group.name, plc.ip, e.currentTarget.value)}>
                {#each STATES as s (s)}
                  <option value={s}>{translate($lang, STATE_KEY[s])}</option>
                {/each}
              </select>
              <select value={plc.recipe ?? ''} onchange={(e) => onRecipeChange(group.name, plc.ip, e.currentTarget.value)}>
                <option value="">{translate($lang, 'service_demo_recipe_none')}</option>
                {#each RECIPES as r (r)}
                  <option value={r}>{r}</option>
                {/each}
              </select>
              <input
                type="checkbox"
                checked={plc.is_online}
                onchange={(e) => onOnlineChange(group.name, plc.ip, e.currentTarget.checked)}
              />
              <input
                type="number"
                min="0"
                step="1"
                class="remaining-input"
                disabled={plc.state !== 'BAKING'}
                value={plc.remaining_seconds ?? ''}
                onchange={(e) => onRemainingChange(group.name, plc.ip, e.currentTarget.value)}
              />
            </div>
          {/each}
        </div>
      </div>
    {/each}
  </div>
{/if}

<style>
  h2 {
    margin: 0 0 clamp(0.75rem, 1.5vh, 1.25rem);
    font-size: var(--font-group-header);
    color: var(--text-primary);
    overflow-wrap: break-word;
  }

  .mode-toggle {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-bottom: clamp(0.75rem, 1.5vh, 1.1rem);
  }

  .mode-toggle button {
    font-size: var(--font-toggle);
    font-weight: 600;
    padding: clamp(0.5rem, 1vh, 0.75rem) clamp(1rem, 1.8vw, 1.5rem);
    border-radius: var(--radius);
    border: 1px solid var(--border-color);
    background: var(--bg-app);
    color: var(--text-secondary);
    white-space: normal;
    overflow-wrap: break-word;
  }

  .mode-toggle button.active {
    background: var(--accent);
    border-color: var(--accent);
    color: var(--opelka-blue-fg);
  }

  .mode-toggle button:disabled {
    opacity: 0.6;
    cursor: default;
  }

  .error {
    margin: 0 0 0.75rem;
    color: var(--danger-bg);
    font-size: var(--font-toggle);
    font-weight: 600;
    overflow-wrap: break-word;
  }

  .demo-controls {
    border-top: 1px solid var(--border-color);
    padding-top: clamp(0.75rem, 1.5vh, 1.1rem);
    margin-top: clamp(0.5rem, 1vh, 0.85rem);
  }

  .demo-controls h3 {
    margin: 0 0 clamp(0.6rem, 1.2vh, 0.9rem);
    font-size: var(--font-toggle);
    font-weight: 600;
    color: var(--text-primary);
  }

  .demo-group {
    margin-bottom: clamp(0.75rem, 1.5vh, 1.1rem);
  }

  .demo-group:last-child {
    margin-bottom: 0;
  }

  .demo-group-name {
    margin: 0 0 0.4rem;
    font-size: var(--font-toggle);
    color: var(--text-primary);
    font-weight: 600;
    overflow-wrap: break-word;
  }

  .demo-group-type {
    color: var(--text-secondary);
    font-weight: 400;
  }

  .demo-table {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    /* Five columns' worth of minmax() floors (unit/state/recipe/online/
       remaining) can need more width than a narrow card has to give —
       scroll horizontally right here rather than forcing .card (and so
       the whole two-card row, and the page) wider. */
    overflow-x: auto;
  }

  .demo-row,
  .demo-row-head {
    min-width: fit-content;
  }

  .demo-row {
    display: grid;
    grid-template-columns:
      minmax(2.5rem, 0.5fr) minmax(6.5rem, 1.2fr) minmax(6.5rem, 1.2fr) minmax(3.5rem, 0.6fr)
      minmax(5.5rem, 0.9fr);
    align-items: center;
    gap: 0.6rem;
    padding: clamp(0.4rem, 0.8vh, 0.6rem) clamp(0.5rem, 1vw, 0.75rem);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    background: var(--bg-app);
  }

  .demo-row-head {
    border: none;
    background: transparent;
    padding: 0 clamp(0.5rem, 1vw, 0.75rem);
    font-size: calc(var(--font-toggle) * 0.85);
    color: var(--text-secondary);
    font-weight: 600;
  }

  .demo-unit {
    font-size: var(--font-toggle);
    color: var(--text-primary);
    font-weight: 600;
  }

  select,
  input[type='number'] {
    font-size: calc(var(--font-toggle) * 0.9);
    padding: clamp(0.35rem, 0.7vh, 0.5rem);
    border-radius: var(--radius);
    border: 1px solid var(--border-color);
    background: var(--bg-panel);
    color: var(--text-primary);
    width: 100%;
    min-width: 0;
  }

  input[type='checkbox'] {
    width: 1.2em;
    height: 1.2em;
    justify-self: start;
  }

  input:disabled {
    opacity: 0.5;
  }
</style>
