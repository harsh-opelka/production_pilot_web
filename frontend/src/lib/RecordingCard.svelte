<script>
  // Service-only (this card is only ever mounted from ServiceHome, which
  // is only reachable at the Service level — see Sidebar.svelte). Wraps
  // the recording-status/recording/history endpoints described in
  // server.py's "History (KPI) logging controls" section.
  import { onMount } from 'svelte';
  import { lang } from './stores.js';
  import { translate } from './translations.js';
  import {
    getRecordingStatus,
    setRecording,
    clearHistory,
    getHistorySummary,
    ServiceApiError,
  } from './serviceApi.js';

  let enabled = $state(false);
  let summary = $state(null);
  let error = $state('');
  let notice = $state('');
  let busy = $state(false);

  function formatTimestamp(ts) {
    if (!ts) return '–';
    const d = new Date(ts);
    return Number.isNaN(d.getTime()) ? ts : d.toLocaleString();
  }

  async function refresh() {
    try {
      const [status, hist] = await Promise.all([getRecordingStatus(), getHistorySummary()]);
      enabled = status.enabled;
      summary = hist;
      error = '';
    } catch (err) {
      error = err instanceof ServiceApiError ? err.message : String(err);
    }
  }

  onMount(refresh);

  async function toggle() {
    error = '';
    notice = '';
    busy = true;
    try {
      await setRecording(!enabled);
      await refresh();
    } catch (err) {
      error = err instanceof ServiceApiError ? err.message : String(err);
    } finally {
      busy = false;
    }
  }

  async function onClearHistory() {
    if (!confirm(translate($lang, 'service_recording_clear_confirm'))) return;
    error = '';
    notice = '';
    busy = true;
    try {
      const result = await clearHistory();
      notice = translate($lang, 'service_recording_cleared', { n: result.deleted_rows });
      await refresh();
    } catch (err) {
      error = err instanceof ServiceApiError ? err.message : String(err);
    } finally {
      busy = false;
    }
  }
</script>

<h2>{translate($lang, 'service_recording_heading')}</h2>

<div class="toggle-row">
  <span class="toggle-label">{translate($lang, 'service_recording_toggle_label')}</span>
  <button
    type="button"
    class="switch"
    class:on={enabled}
    role="switch"
    aria-checked={enabled}
    aria-label={translate($lang, 'service_recording_toggle_label')}
    disabled={busy}
    onclick={toggle}
  >
    <span class="knob"></span>
  </button>
  <span class="toggle-state">
    {translate($lang, enabled ? 'service_recording_status_on' : 'service_recording_status_off')}
  </span>
</div>

{#if summary}
  <div class="summary">
    {#if summary.total_rows === 0}
      <p>{translate($lang, 'service_recording_summary_empty')}</p>
    {:else}
      <p>{translate($lang, 'service_recording_row_count', { n: summary.total_rows })}</p>
      <p>{translate($lang, 'service_recording_earliest')}: {formatTimestamp(summary.earliest_timestamp)}</p>
      <p>{translate($lang, 'service_recording_latest')}: {formatTimestamp(summary.latest_timestamp)}</p>
    {/if}
  </div>
{/if}

{#if error}
  <p class="error">{error}</p>
{/if}
{#if notice}
  <p class="success">{notice}</p>
{/if}

<button type="button" class="clear-button" disabled={busy} onclick={onClearHistory}>
  {translate($lang, 'service_recording_clear_button')}
</button>

<style>
  h2 {
    margin: 0 0 clamp(0.75rem, 1.5vh, 1.25rem);
    font-size: var(--font-group-header);
    color: var(--text-primary);
  }

  .toggle-row {
    display: flex;
    align-items: center;
    gap: clamp(0.5rem, 1vw, 0.85rem);
    margin-bottom: clamp(0.75rem, 1.5vh, 1.1rem);
  }

  .toggle-label {
    font-size: var(--font-toggle);
    color: var(--text-secondary);
  }

  .switch {
    flex: 0 0 auto;
    width: 2.6em;
    height: 1.5em;
    border-radius: 999px;
    border: 1px solid var(--border-color);
    background: var(--bg-app);
    padding: 0.15em;
    display: flex;
    align-items: center;
    justify-content: flex-start;
    transition: background 0.15s;
  }

  .switch.on {
    background: var(--state-baking);
    justify-content: flex-end;
  }

  .switch:disabled {
    opacity: 0.6;
    cursor: default;
  }

  .knob {
    width: 1.1em;
    height: 1.1em;
    border-radius: 50%;
    background: #ffffff;
  }

  .toggle-state {
    font-size: var(--font-toggle);
    font-weight: 600;
    color: var(--text-primary);
  }

  .summary {
    font-size: var(--font-tile-sub);
    color: var(--text-secondary);
    margin-bottom: clamp(0.75rem, 1.5vh, 1.1rem);
  }

  .summary p {
    margin: 0.2em 0;
  }

  .error {
    margin: 0 0 0.75rem;
    color: var(--danger-bg);
    font-size: var(--font-toggle);
    font-weight: 600;
  }

  .success {
    margin: 0 0 0.75rem;
    color: var(--state-baking);
    font-size: var(--font-toggle);
    font-weight: 600;
  }

  .clear-button {
    font-size: var(--font-toggle);
    font-weight: 600;
    padding: clamp(0.5rem, 1vh, 0.75rem) clamp(1.1rem, 2vw, 1.75rem);
    border: 1px solid var(--danger-bg);
    border-radius: var(--radius);
    background: transparent;
    color: var(--danger-bg);
  }

  .clear-button:disabled {
    opacity: 0.5;
    cursor: default;
  }
</style>
