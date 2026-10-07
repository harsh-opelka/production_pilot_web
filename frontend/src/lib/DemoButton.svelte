<script>
  // Customer Demo Mode button (Dashboard toolbar, next to Block/List View).
  //   click        -> play the recorded demo (DemoOverlay.svelte)
  //   hover / focus / tap on ▾ (Service only) -> floating menu: Record, Stop
  // While recording it turns red: "● REC 00:42". Who sees it: Service
  // always; everyone else only when the Service setting "Show Demo button
  // for all users" is on — and only Service can Record/Stop.
  import { lang, auth, nowTick } from './stores.js';
  import { translate } from './translations.js';
  import {
    demoStatus,
    loadDemoStatus,
    demoMessage,
    displayMode,
    showDemoMessage,
    canManageDemo,
    demoButtonVisible,
    recordSupport,
    menuEntries,
    formatClock,
  } from './demoMode.js';
  import { recorder, startRecording, stopRecording, retrySave, downloadRecording } from './demoRecorder.js';

  let open = $state(false);
  let confirmReplace = $state(false);
  let wrapEl = $state();

  let manage = $derived(canManageDemo($auth.level));
  let visible = $derived(demoButtonVisible($auth.level, $demoStatus.show_for_all) || $recorder.phase !== 'idle');
  let support = recordSupport();
  let entries = $derived(menuEntries($recorder.phase, support));
  let recording = $derived($recorder.phase === 'recording');
  let recTime = $derived(recording && $recorder.startedAt ? formatClock(($nowTick - $recorder.startedAt) / 1000) : '');

  async function play() {
    if ($recorder.phase !== 'idle' && $recorder.phase !== 'failed') {
      // Don't cover a running recording / upload with the player — the menu offers Stop.
      if (manage) open = true;
      return;
    }
    open = false;
    // Fresh status: the demo may have been recorded / replaced / deleted
    // from another screen since this page loaded. No answer = the server
    // isn't reachable: say so instead of opening a player that can't load.
    if (!(await loadDemoStatus())) {
      showDemoMessage('demo_server_unreachable');
      return;
    }
    if (!$demoStatus.exists) {
      showDemoMessage(manage ? 'demo_none' : 'demo_none_viewer');
      return;
    }
    open = false;
    displayMode.set('demo');
  }

  function chooseRecord() {
    if (!entries.record.enabled) return;
    open = false;
    if ($demoStatus.exists) confirmReplace = true;
    else startRecording();
  }

  // The Replace click is a fresh user gesture, which the browser requires
  // to open its share prompt (a native confirm() wouldn't provide one).
  function replaceAndRecord() {
    confirmReplace = false;
    startRecording();
  }

  function chooseStop() {
    if (!entries.stop.enabled) return;
    open = false;
    stopRecording('user');
  }

  function onWindowPointerdown(event) {
    if (open && wrapEl && !wrapEl.contains(event.target)) open = false;
  }

  function onFocusOut(event) {
    if (wrapEl && !wrapEl.contains(event.relatedTarget)) open = false;
  }

  function onKeydown(event) {
    if (event.key === 'Escape') {
      open = false;
      confirmReplace = false;
    }
  }
</script>

<svelte:window onpointerdown={onWindowPointerdown} onkeydown={onKeydown} />

{#if visible}
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="demo-wrap"
    bind:this={wrapEl}
    onmouseenter={() => manage && (open = true)}
    onmouseleave={() => (open = false)}
    onfocusin={() => manage && (open = true)}
    onfocusout={onFocusOut}
  >
    <div class="demo-group" class:rec={recording}>
      <button type="button" class="demo-button" onclick={play}>
        {#if recording}
          <span class="dot" aria-hidden="true"></span>
          {translate($lang, 'demo_rec')} {recTime}
        {:else if $recorder.phase === 'saving'}
          {translate($lang, 'demo_saving')}{$recorder.progress != null ? ` ${Math.round($recorder.progress * 100)}%` : ''}
        {:else}
          {translate($lang, 'demo')}
        {/if}
      </button>
      {#if manage}
        <button
          type="button"
          class="demo-arrow"
          aria-label={translate($lang, 'demo_menu')}
          aria-haspopup="menu"
          aria-expanded={open}
          onclick={() => (open = true)}
        >▾</button>
      {/if}
    </div>

    {#if open && manage}
      <!-- Floats (absolute) right under the button; padding-top instead of a
           margin so the mouse can move into it without leaving the wrapper. -->
      <div class="menu-float">
        <div class="menu" role="menu">
          <button type="button" role="menuitem" disabled={!entries.record.enabled} onclick={chooseRecord}>
            <span class="rec-icon" aria-hidden="true">●</span> {translate($lang, 'demo_record')}
          </button>
          <button type="button" role="menuitem" disabled={!entries.stop.enabled} onclick={chooseStop}>
            <span class="stop-icon" aria-hidden="true">■</span> {translate($lang, 'demo_stop')}
          </button>
          {#if entries.record.reasonKey}
            <p class="menu-note">{translate($lang, entries.record.reasonKey)}</p>
          {/if}
        </div>
      </div>
    {/if}

    {#if $recorder.phase === 'failed' && manage}
      <!-- Saving failed: the recording is still in this browser. -->
      <div class="demo-msg failed" role="alert">
        <p>{translate($lang, 'demo_save_failed_kept')}</p>
        <p class="reason">{translate($lang, $recorder.error.key, $recorder.error.vars)}</p>
        <div class="failed-actions">
          <button type="button" class="primary" onclick={retrySave}>{translate($lang, 'demo_retry_save')}</button>
          <button type="button" class="secondary" onclick={downloadRecording}>{translate($lang, 'demo_download')}</button>
        </div>
      </div>
    {:else if $recorder.phase === 'prompt'}
      <p class="demo-msg">{translate($lang, 'demo_share_hint')}</p>
    {:else if $demoMessage}
      <p class="demo-msg">{translate($lang, $demoMessage.key, $demoMessage.vars)}</p>
    {/if}
  </div>
{/if}

{#if confirmReplace}
  <div class="modal-backdrop">
    <div class="modal" role="alertdialog" aria-modal="true" aria-labelledby="demo-replace-title">
      <p id="demo-replace-title">{translate($lang, 'demo_replace_title')}</p>
      <div class="modal-actions">
        <button type="button" class="secondary" onclick={() => (confirmReplace = false)}>{translate($lang, 'cancel')}</button>
        <button type="button" class="primary" onclick={replaceAndRecord}>{translate($lang, 'demo_replace')}</button>
      </div>
    </div>
  </div>
{/if}

<style>
  /* Same size/shape as the Block/List toggle next to it (ViewToggle.svelte). */
  .demo-wrap {
    position: relative;
    display: inline-flex;
    flex-direction: column;
    align-items: flex-end;
  }

  .demo-group {
    display: inline-flex;
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    overflow: hidden;
    background: var(--opelka-blue);
  }

  .demo-group button {
    font: inherit;
    font-size: clamp(0.75rem, 0.85vw, 0.95rem);
    font-weight: 600;
    color: var(--opelka-blue-fg);
    background: none;
    border: none;
    cursor: pointer;
  }

  .demo-button {
    padding: clamp(0.25rem, 0.4vh, 0.4rem) clamp(0.55rem, 0.9vw, 0.9rem);
    display: inline-flex;
    align-items: center;
    gap: 0.4em;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }

  .demo-group .demo-arrow {
    padding: 0 clamp(0.4rem, 0.6vw, 0.6rem);
    border-left: 1px solid rgba(255, 255, 255, 0.25);
  }

  .demo-group.rec {
    background: var(--danger-bg);
    border-color: var(--danger-bg);
  }

  .dot {
    width: 0.6em;
    height: 0.6em;
    border-radius: 50%;
    background: #ffffff;
    animation: pulse 1.2s ease-in-out infinite;
  }

  @keyframes pulse {
    50% {
      opacity: 0.25;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .dot {
      animation: none;
    }
  }

  .menu-float {
    position: absolute;
    top: 100%;
    right: 0;
    z-index: 50;
    padding-top: 0.3rem;
  }

  .menu {
    min-width: 11rem;
    display: flex;
    flex-direction: column;
    padding: 0.3rem 0;
    background: var(--bg-panel);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.25);
  }

  .menu button {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 0.9rem;
    font: inherit;
    font-size: var(--font-tile-sub);
    text-align: left;
    color: var(--text-primary);
    background: none;
    border: none;
    cursor: pointer;
  }

  .menu button:hover:not(:disabled),
  .menu button:focus-visible {
    background: var(--bg-app);
  }

  .menu button:disabled {
    opacity: 0.45;
    cursor: default;
  }

  .rec-icon {
    color: var(--danger-bg);
  }

  .menu-note {
    margin: 0.2rem 0.9rem 0.4rem;
    max-width: 16rem;
    font-size: 0.8rem;
    color: var(--text-secondary);
  }

  .demo-msg {
    position: absolute;
    top: calc(100% + 0.3rem);
    right: 0;
    z-index: 40;
    width: max-content;
    max-width: min(22rem, 80vw);
    margin: 0;
    padding: 0.45rem 0.7rem;
    font-size: 0.85rem;
    color: var(--text-primary);
    background: var(--bg-panel);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.2);
  }

  .demo-msg.failed p {
    margin: 0 0 0.35rem;
  }

  .demo-msg.failed .reason {
    color: var(--danger-bg);
    font-weight: 600;
  }

  .failed-actions {
    display: flex;
    gap: 0.5rem;
    margin-top: 0.4rem;
  }

  .failed-actions button {
    font: inherit;
    font-size: 0.85rem;
    font-weight: 600;
    padding: 0.35rem 0.75rem;
    border-radius: var(--radius);
    cursor: pointer;
  }

  /* The menu wins over a message while both would show. */
  .menu-float ~ .demo-msg {
    display: none;
  }

  .modal-backdrop {
    position: fixed;
    inset: 0;
    z-index: 2000;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(0, 0, 0, 0.45);
  }

  .modal {
    min-width: min(24rem, 90vw);
    padding: 1.25rem 1.5rem;
    background: var(--bg-panel);
    color: var(--text-primary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.35);
  }

  .modal p {
    margin: 0 0 1.1rem;
    font-size: var(--font-toggle);
    font-weight: 600;
  }

  .modal-actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.75rem;
  }

  .modal-actions button {
    font: inherit;
    font-weight: 600;
    padding: 0.5rem 1.1rem;
    border-radius: var(--radius);
    cursor: pointer;
  }

  .primary {
    border: none;
    background: var(--accent);
    color: var(--opelka-blue-fg);
  }

  .secondary {
    border: 1px solid var(--border-color);
    background: none;
    color: var(--text-primary);
  }
</style>
