<script>
  // Service: Customer Demo Mode settings — who sees the Demo (play) button,
  // the current recording's details, and deleting it. Recording happens
  // from the Demo button on the Dashboard (hover -> Record).
  import { lang } from './stores.js';
  import { translate } from './translations.js';
  import { demoStatus, loadDemoStatus, formatClock } from './demoMode.js';
  import { setDemoSettings, deleteDemoVideo, ServiceApiError } from './serviceApi.js';

  let busy = $state(false);
  let error = $state('');

  loadDemoStatus();

  function sizeText(bytes) {
    return bytes >= 1024 * 1024 ? `${(bytes / (1024 * 1024)).toFixed(1)} MB` : `${Math.ceil(bytes / 1024)} KB`;
  }

  function dateText(iso) {
    return iso ? new Date(iso).toLocaleString($lang === 'de' ? 'de-DE' : 'en-GB', { dateStyle: 'short', timeStyle: 'short' }) : '';
  }

  async function run(action) {
    error = '';
    busy = true;
    try {
      demoStatus.set({ ...(await action()), loaded: true });
    } catch (err) {
      error = err instanceof ServiceApiError ? err.message : String(err);
    } finally {
      busy = false;
    }
  }

  function toggleShowForAll(event) {
    const value = event.currentTarget.checked;
    run(() => setDemoSettings(value));
  }

  function remove() {
    if (!window.confirm(translate($lang, 'service_customer_demo_delete_confirm'))) return;
    run(() => deleteDemoVideo());
  }
</script>

<h2>{translate($lang, 'service_customer_demo_heading')}</h2>
<p class="help">{translate($lang, 'service_customer_demo_help')}</p>

<label class="toggle">
  <input type="checkbox" checked={$demoStatus.show_for_all} disabled={busy} onchange={toggleShowForAll} />
  <span>{translate($lang, 'service_customer_demo_show_all')}</span>
</label>
<p class="note">{translate($lang, 'service_customer_demo_show_all_note')}</p>

<p class="status">
  {#if $demoStatus.exists}
    {translate($lang, 'service_customer_demo_recorded', {
      date: dateText($demoStatus.recorded_at),
      length: formatClock($demoStatus.duration_seconds ?? 0),
      size: sizeText($demoStatus.size_bytes ?? 0),
    })}
  {:else}
    {translate($lang, 'service_customer_demo_none')}
  {/if}
</p>

{#if error}<p class="error">{error}</p>{/if}

<button type="button" class="danger" disabled={busy || !$demoStatus.exists} onclick={remove}>
  {translate($lang, 'service_customer_demo_delete')}
</button>

<style>
  h2 {
    margin: 0 0 clamp(0.75rem, 1.5vh, 1.25rem);
    font-size: var(--font-group-header);
    color: var(--text-primary);
  }

  .help,
  .note,
  .status {
    margin: 0 0 clamp(0.65rem, 1.2vh, 1rem);
    color: var(--text-secondary);
    font-size: var(--font-toggle);
  }

  .note {
    font-size: var(--font-tile-sub);
  }

  .status {
    color: var(--text-primary);
  }

  .toggle {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    margin-bottom: 0.4rem;
    font-size: var(--font-toggle);
    color: var(--text-primary);
    cursor: pointer;
  }

  .toggle input {
    width: 1.2rem;
    height: 1.2rem;
  }

  .error {
    margin: 0 0 0.75rem;
    color: var(--danger-bg);
    font-size: var(--font-toggle);
    font-weight: 600;
  }

  .danger {
    font-size: var(--font-toggle);
    font-weight: 600;
    padding: clamp(0.5rem, 1vh, 0.75rem) clamp(1.1rem, 2vw, 1.75rem);
    border: none;
    border-radius: var(--radius);
    background: var(--danger-bg);
    color: var(--danger-fg);
    cursor: pointer;
  }

  .danger:disabled {
    opacity: 0.5;
    cursor: default;
  }
</style>
