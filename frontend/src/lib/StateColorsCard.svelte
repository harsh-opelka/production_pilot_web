<script>
  // Service: set and save the machine-state colours (PUT /api/state-colors).
  // Every change shows at once in that state's preview tile — a real
  // FryerTile fed the unsaved colours via CSS variables on its wrapper —
  // but reaches the dashboards only on Save (then every open dashboard,
  // the TV included, re-fetches them via the state payload's
  // colors_version). Defaults come from the backend (GET's `defaults`).
  import { onDestroy } from 'svelte';
  import { lang, leaveGuard } from './stores.js';
  import { translate } from './translations.js';
  import { saveStateColors, ServiceApiError } from './serviceApi.js';
  import {
    STATE_COLOR_SLOTS,
    MIN_CONTRAST,
    applyStateColors,
    textForSlot,
    findSimilarPairs,
    loadStateColors,
    normalizeHex,
    stateColorVars,
    stateColors,
  } from './stateColors.js';
  import ColorPicker from './ColorPicker.svelte';
  import FryerTile from './FryerTile.svelte';

  let saved = $state(null); // {slot: hex} as on the server
  let draft = $state(null); // {slot: hex} being edited
  let hexText = $state({}); // {slot: text in the hex field}
  let hexErrors = $state({}); // {slot: inline error}
  let saving = $state(false);
  let error = $state('');
  let success = $state('');

  let defaults = $derived($stateColors.defaults);
  let dirty = $derived(!!saved && !!draft && STATE_COLOR_SLOTS.some(({ key }) => draft[key] !== saved[key]));
  let similar = $derived(draft ? findSimilarPairs(draft) : []);

  // Take over the server's colours whenever they change and nothing is
  // being edited (first load, or another device saved).
  $effect(() => {
    const colors = $stateColors.colors;
    if (!colors) {
      loadStateColors();
      return;
    }
    if (!dirty) {
      saved = { ...colors };
      draft = { ...colors };
      hexText = { ...colors };
      hexErrors = {};
    }
  });

  // Leaving the page (sidebar, logout, closing the tab) with unsaved
  // changes asks first — see stores.js confirmLeave().
  $effect(() => {
    leaveGuard.set(dirty ? translate($lang, 'service_colors_leave_confirm') : null);
  });
  function onBeforeUnload(event) {
    if (dirty) event.preventDefault();
  }
  onDestroy(() => leaveGuard.set(null));

  function setColor(key, hex) {
    draft = { ...draft, [key]: hex };
    hexText = { ...hexText, [key]: hex };
    hexErrors = { ...hexErrors, [key]: '' };
    success = '';
  }

  // Invalid input keeps the old colour and shows an inline error.
  function commitHexText(key) {
    const n = normalizeHex(hexText[key]);
    if (!n) {
      hexErrors = { ...hexErrors, [key]: translate($lang, 'service_colors_invalid_hex') };
      return;
    }
    setColor(key, n);
  }

  function resetOne(key) {
    if (defaults) setColor(key, defaults[key]);
  }

  // Back to the defaults in the editor; like every other change it takes
  // effect on Save.
  function resetAll() {
    if (!defaults || !window.confirm(translate($lang, 'service_colors_reset_all_confirm'))) return;
    draft = { ...defaults };
    hexText = { ...defaults };
    hexErrors = {};
    success = '';
  }

  async function save() {
    error = '';
    success = '';
    saving = true;
    try {
      const result = await saveStateColors(draft);
      saved = { ...result.colors };
      draft = { ...result.colors };
      hexText = { ...result.colors };
      applyStateColors(result); // this browser right away; the others via colors_version
      success = translate($lang, 'service_colors_saved');
    } catch (err) {
      error = err instanceof ServiceApiError ? err.message : String(err);
    } finally {
      saving = false;
    }
  }

  function labelOf(key) {
    return translate($lang, STATE_COLOR_SLOTS.find((s) => s.key === key).labelKey);
  }

  // A realistic tile per slot: number, state, time, recipe, temperature.
  const enteredAt = new Date(Date.now() - 754_000).toISOString();
  const PREVIEW = {
    waiting: { state: 'WAITING' },
    baking: { state: 'BAKING', remaining_seconds: 245 },
    near_completion: { state: 'BAKING', remaining_seconds: 20, near_completion: true },
    heating: { state: 'HEATING', oil_temp_current: 118 },
    hot: { state: 'HOT', oil_temp_current: 64 },
    cold: { state: 'COLD', oil_temp_current: 24 },
    blocked: { state: 'BLOCKED' },
    error: { state: 'ERROR' },
    standby: { state: 'STANDBY', oil_temp_current: null },
  };
  function previewPlc(key, index) {
    return {
      ip: `preview-${key}`,
      unit_number: index + 1,
      is_online: true,
      remaining_seconds: null,
      recipe_name: 'Berliners',
      oil_temp_current: 180,
      oil_temp_target: 180,
      near_completion: false,
      state_entered_at: enteredAt,
      ...PREVIEW[key],
    };
  }

  function varsStyle(colors) {
    return Object.entries(stateColorVars(colors))
      .map(([name, value]) => `${name}: ${value}`)
      .join('; ');
  }
</script>

<svelte:window onbeforeunload={onBeforeUnload} />

<div class="header">
  <div>
    <h2>{translate($lang, 'service_colors_heading')}</h2>
    <p class="help">{translate($lang, 'service_colors_help')}</p>
  </div>
  <div class="actions">
    {#if dirty}<span class="hint">{translate($lang, 'service_layout_unsaved')}</span>{/if}
    <button type="button" class="link" onclick={resetAll} disabled={!defaults}>
      {translate($lang, 'service_colors_reset_all')}
    </button>
    <button type="button" class="primary" onclick={save} disabled={saving || !dirty}>
      {translate($lang, 'service_save')}
    </button>
  </div>
</div>

{#if error}<p class="error">{error}</p>{/if}
{#if success}<p class="success">{success}</p>{/if}
{#each similar as [a, b] (a + b)}
  <p class="warning">⚠ {translate($lang, 'service_colors_similar', { a: labelOf(a), b: labelOf(b) })}</p>
{/each}

{#if draft}
  <div class="slots" style={varsStyle(draft)}>
    {#each STATE_COLOR_SLOTS as slot, index (slot.key)}
      {@const contrast = textForSlot(slot.key, draft[slot.key])}
      <div class="slot">
        <div class="slot-head">
          <span class="name">{translate($lang, slot.labelKey)}</span>
          {#if defaults && draft[slot.key] !== defaults[slot.key]}
            <button type="button" class="link small" onclick={() => resetOne(slot.key)}>
              {translate($lang, 'service_colors_reset')}
            </button>
          {/if}
        </div>
        <div class="controls">
          <ColorPicker
            value={draft[slot.key]}
            label={translate($lang, slot.labelKey)}
            onchange={(hex) => setColor(slot.key, hex)}
          />
          <input
            class="hex"
            type="text"
            maxlength="9"
            spellcheck="false"
            aria-label={translate($lang, 'service_colors_hex')}
            aria-invalid={hexErrors[slot.key] ? 'true' : 'false'}
            bind:value={hexText[slot.key]}
            onchange={() => commitHexText(slot.key)}
            onkeydown={(e) => e.key === 'Enter' && commitHexText(slot.key)}
          />
          {#if contrast.ratio < MIN_CONTRAST}
            <span class="contrast-warning" title={translate($lang, 'service_colors_low_contrast', { ratio: contrast.ratio.toFixed(1) })}>
              ⚠ {contrast.ratio.toFixed(1)}:1
            </span>
          {/if}
        </div>
        {#if hexErrors[slot.key]}<p class="error small">{hexErrors[slot.key]}</p>{/if}
        <div class="preview" aria-hidden="true">
          <FryerTile plc={previewPlc(slot.key, index)} language={$lang} />
        </div>
        <!-- Below the tile, so every preview tile starts at the same height. -->
        {#if slot.key === 'heating'}
          <p class="note">{translate($lang, 'service_colors_heating_note')}</p>
        {:else if slot.key === 'blocked'}
          <p class="note">{translate($lang, 'service_colors_blocked_note')}</p>
        {/if}
      </div>
    {/each}
  </div>
{/if}

<style>
  .header {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
  }

  h2 {
    margin: 0 0 clamp(0.5rem, 1vh, 0.9rem);
    font-size: var(--font-group-header);
    color: var(--text-primary);
  }

  .help {
    margin: 0 0 clamp(0.65rem, 1.2vh, 1rem);
    max-width: 50rem;
    color: var(--text-secondary);
    font-size: var(--font-toggle);
  }

  .actions {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 1rem;
  }

  .hint {
    color: var(--text-secondary);
    font-size: var(--font-tile-sub);
    font-style: italic;
  }

  button {
    font: inherit;
    cursor: pointer;
  }

  button:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .primary {
    font-size: var(--font-toggle);
    font-weight: 600;
    padding: clamp(0.5rem, 1vh, 0.75rem) clamp(1.1rem, 2vw, 1.75rem);
    border: none;
    border-radius: var(--radius);
    background: var(--accent);
    color: var(--opelka-blue-fg);
  }

  .link {
    background: none;
    border: none;
    padding: 0;
    color: var(--text-primary);
    text-decoration: underline;
    font-size: var(--font-tile-sub);
  }

  .link.small {
    font-size: 0.85rem;
    color: var(--text-secondary);
  }

  .error,
  .success,
  .warning {
    margin: 0 0 0.5rem;
    font-size: var(--font-toggle);
    font-weight: 600;
  }

  .error {
    color: var(--danger-bg);
  }

  .error.small {
    margin: 0.35rem 0 0;
    font-size: 0.85rem;
  }

  .success {
    color: var(--state-baking);
  }

  .warning {
    color: var(--text-primary);
  }

  .slots {
    margin-top: 0.75rem;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(min(100%, 15rem), 1fr));
    gap: clamp(1rem, 2vw, 1.75rem);
  }

  .slot {
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .slot-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 0.5rem;
  }

  .name {
    font-weight: 600;
    color: var(--text-primary);
    font-size: var(--font-toggle);
  }

  .controls {
    display: flex;
    align-items: center;
    gap: 0.6rem;
  }

  .hex {
    width: 6.5rem;
    padding: 0.4rem 0.5rem;
    font-family: ui-monospace, monospace;
    font-size: 0.95rem;
    text-transform: uppercase;
    background: var(--bg-app);
    color: var(--text-primary);
    border: 1px solid var(--border-color);
    border-radius: 0.35rem;
  }

  .hex[aria-invalid='true'] {
    border-color: var(--danger-bg);
  }

  .contrast-warning {
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--danger-bg);
    white-space: nowrap;
  }

  .note {
    margin: 0;
    font-size: 0.85rem;
    color: var(--text-secondary);
  }

  /* Room for the tile's shadow; the tile itself keeps its real size. */
  .preview {
    padding: 0.25rem;
  }
</style>
