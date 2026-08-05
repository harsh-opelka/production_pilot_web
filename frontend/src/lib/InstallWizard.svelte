<script>
  import { onMount } from 'svelte';
  import { lang } from './stores.js';
  import { translate } from './translations.js';
  import { scanNetwork, getServiceConfig, saveServiceConfig, ServiceApiError } from './serviceApi.js';

  let { onClose } = $props();

  const MACHINE_TYPES = ['STANDALONE', 'DUO', 'TRIO', 'QUATTRO'];
  const TYPE_BY_COUNT = { 1: 'STANDALONE', 2: 'DUO', 3: 'TRIO', 4: 'QUATTRO' };

  // --- Section 1: scan ----------------------------------------------
  let subnet = $state('192.168.178.0/24');
  let port = $state(4841);
  let scanning = $state(false);
  let scanError = $state('');
  let scanResults = $state([]); // [{ip, port, server_name}]
  let checkedIps = $state(/** @type {Set<string>} */ (new Set()));

  // --- Section 2: machines (pre-populated from existing config) -----
  let groups = $state([]); // [{name, type, plcs: [ip,...]}]
  let loadingConfig = $state(true);
  let configLoadError = $state('');

  let assignedIps = $derived(new Set(groups.flatMap((g) => g.plcs)));
  let availableDevices = $derived(scanResults.filter((d) => !assignedIps.has(d.ip)));

  // --- Create-group form ----------------------------------------------
  let showCreateForm = $state(false);
  let createName = $state('');
  let createType = $state('STANDALONE');
  let createIps = $state(/** @type {string[]} */ ([]));
  let createNameError = $state('');

  // --- Save -------------------------------------------------------------
  let saving = $state(false);
  let saveError = $state('');
  let saveSuccess = $state(false);
  let showEmptyConfirm = $state(false);

  onMount(async () => {
    try {
      const config = await getServiceConfig();
      groups = (config.machines ?? []).map((m) => ({ name: m.name, type: m.type, plcs: [...m.plcs] }));
    } catch (err) {
      configLoadError = err.message;
    } finally {
      loadingConfig = false;
    }
  });

  async function runScan() {
    scanError = '';
    scanning = true;
    checkedIps = new Set();
    try {
      const result = await scanNetwork(subnet, Number(port));
      scanResults = result.devices;
    } catch (err) {
      scanResults = [];
      scanError = translate($lang, 'service_scan_error', { error: err.message });
    } finally {
      scanning = false;
    }
  }

  function toggleChecked(ip) {
    const next = new Set(checkedIps);
    if (next.has(ip)) next.delete(ip);
    else next.add(ip);
    checkedIps = next;
  }

  function openCreateForm() {
    createIps = availableDevices.filter((d) => checkedIps.has(d.ip)).map((d) => d.ip);
    createType = TYPE_BY_COUNT[createIps.length] ?? 'QUATTRO';
    createName = '';
    createNameError = '';
    showCreateForm = true;
  }

  function moveUp(index) {
    if (index === 0) return;
    const next = [...createIps];
    [next[index - 1], next[index]] = [next[index], next[index - 1]];
    createIps = next;
  }

  function moveDown(index) {
    if (index === createIps.length - 1) return;
    const next = [...createIps];
    [next[index], next[index + 1]] = [next[index + 1], next[index]];
    createIps = next;
  }

  function confirmCreateGroup() {
    if (!createName.trim()) {
      createNameError = translate($lang, 'wizard_name_required_msg');
      return;
    }
    groups = [...groups, { name: createName.trim(), type: createType, plcs: [...createIps] }];
    checkedIps = new Set();
    showCreateForm = false;
  }

  function cancelCreateForm() {
    showCreateForm = false;
  }

  function removeGroup(index) {
    groups = groups.filter((_, i) => i !== index);
  }

  function requestSave() {
    // Saving zero groups clears plc_config.json entirely — destructive
    // enough (dashboard goes blank until reconfigured) to confirm first,
    // rather than let a technician nuke the config with one misclick.
    if (groups.length === 0) {
      showEmptyConfirm = true;
      return;
    }
    performSave();
  }

  function cancelEmptyConfirm() {
    showEmptyConfirm = false;
  }

  function confirmEmptySave() {
    showEmptyConfirm = false;
    performSave();
  }

  async function performSave() {
    saveError = '';
    saveSuccess = false;
    saving = true;
    try {
      await saveServiceConfig(groups.map((g) => ({ name: g.name, type: g.type, plcs: g.plcs })));
      saveSuccess = true;
    } catch (err) {
      saveError =
        err instanceof ServiceApiError
          ? translate($lang, 'service_config_save_failed', { error: err.message })
          : err.message;
    } finally {
      saving = false;
    }
  }
</script>

<div class="overlay">
  <div class="modal">
    <header class="modal-header">
      <h1>{translate($lang, 'wizard_heading')}</h1>
      <button class="icon-button" onclick={onClose} aria-label={translate($lang, 'close')}>✕</button>
    </header>

    <div class="modal-body">
      <!-- Section 1: scan -->
      <section>
        <h2>{translate($lang, 'wizard_scan_section')}</h2>

        <div class="scan-form">
          <label class="field">
            <span>{translate($lang, 'wizard_subnet_label')}</span>
            <input type="text" bind:value={subnet} disabled={scanning} />
          </label>
          <label class="field port-field">
            <span>{translate($lang, 'wizard_port_label')}</span>
            <input type="number" bind:value={port} disabled={scanning} />
          </label>
          <button class="primary" onclick={runScan} disabled={scanning || !subnet}>
            {scanning ? translate($lang, 'wizard_scanning') : translate($lang, 'wizard_scan_button')}
          </button>
        </div>

        {#if scanning}
          <p class="in-progress">{translate($lang, 'wizard_scanning')}</p>
        {/if}

        {#if scanError}
          <p class="error">{scanError}</p>
        {/if}

        {#if !scanning && scanResults.length > 0}
          <p class="hint">{translate($lang, 'wizard_found_devices', { n: scanResults.length })}</p>
          <ul class="device-list">
            {#each availableDevices as device (device.ip)}
              <li>
                <label class="device">
                  <input
                    type="checkbox"
                    checked={checkedIps.has(device.ip)}
                    onchange={() => toggleChecked(device.ip)}
                  />
                  <span class="device-ip">{device.ip}</span>
                  <span class="device-name">{device.server_name}</span>
                </label>
              </li>
            {/each}
          </ul>
          <button class="secondary" onclick={openCreateForm} disabled={checkedIps.size === 0}>
            {translate($lang, 'wizard_create_machine_button')}
          </button>
        {:else if !scanning && !scanError}
          <p class="hint">{translate($lang, 'wizard_no_devices_found')}</p>
        {/if}
      </section>

      <!-- Section 2: machines -->
      <section>
        <h2>{translate($lang, 'wizard_machines_section')}</h2>

        {#if showCreateForm}
          <div class="create-form">
            <h3>{translate($lang, 'wizard_create_title')}</h3>
            <p class="hint">{translate($lang, 'wizard_plcs_selected', { n: createIps.length })}</p>

            <label class="field">
              <span>{translate($lang, 'wizard_machine_name_label')}</span>
              <input
                type="text"
                bind:value={createName}
                placeholder={translate($lang, 'wizard_machine_name_placeholder')}
              />
            </label>
            {#if createNameError}
              <p class="error">{createNameError}</p>
            {/if}

            <label class="field">
              <span>{translate($lang, 'wizard_machine_type_label')}</span>
              <select bind:value={createType}>
                {#each MACHINE_TYPES as t (t)}
                  <option value={t}>{t}</option>
                {/each}
              </select>
            </label>

            <div class="priority-list">
              <p class="hint">{translate($lang, 'wizard_priority_order_label')}</p>
              <ol>
                {#each createIps as ip, index (ip)}
                  <li>
                    <span class="priority-ip">{ip}</span>
                    <span class="priority-buttons">
                      <button
                        type="button"
                        onclick={() => moveUp(index)}
                        disabled={index === 0}
                      >
                        {translate($lang, 'wizard_move_up_button')}
                      </button>
                      <button
                        type="button"
                        onclick={() => moveDown(index)}
                        disabled={index === createIps.length - 1}
                      >
                        {translate($lang, 'wizard_move_down_button')}
                      </button>
                    </span>
                  </li>
                {/each}
              </ol>
            </div>

            <div class="form-actions">
              <button class="secondary" onclick={cancelCreateForm}>{translate($lang, 'cancel')}</button>
              <button class="primary" onclick={confirmCreateGroup}>{translate($lang, 'create')}</button>
            </div>
          </div>
        {/if}

        {#if loadingConfig}
          <p class="hint">{translate($lang, 'wizard_scanning')}</p>
        {:else if configLoadError}
          <p class="error">{configLoadError}</p>
        {:else if groups.length === 0}
          <p class="hint">{translate($lang, 'wizard_no_machines')}</p>
        {:else}
          <div class="groups-panel">
            {#each groups as group, index (group.name + index)}
              <div class="group-card">
                <div class="group-card-header">
                  <h3>{group.name} <span class="group-type">({group.type})</span></h3>
                  <button class="secondary" onclick={() => removeGroup(index)}>
                    {translate($lang, 'wizard_remove_button')}
                  </button>
                </div>
                <ol class="group-ips">
                  {#each group.plcs as ip (ip)}
                    <li>{ip}</li>
                  {/each}
                </ol>
              </div>
            {/each}
          </div>
        {/if}
      </section>
    </div>

    <footer class="modal-footer">
      {#if saveError}
        <p class="error">{saveError}</p>
      {/if}
      {#if saveSuccess}
        <p class="success">{translate($lang, 'service_config_saved')}</p>
      {/if}
      <button class="primary" onclick={requestSave} disabled={saving}>
        {translate($lang, 'wizard_save_button')}
      </button>
    </footer>
  </div>
</div>

{#if showEmptyConfirm}
  <div class="overlay confirm-overlay">
    <div class="modal confirm-dialog">
      <h2>{translate($lang, 'wizard_confirm_empty_title')}</h2>
      <p>{translate($lang, 'wizard_confirm_empty_message')}</p>
      <div class="form-actions">
        <button class="secondary" onclick={cancelEmptyConfirm}>{translate($lang, 'cancel')}</button>
        <button class="primary danger" onclick={confirmEmptySave}>
          {translate($lang, 'wizard_confirm_button')}
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.55);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 100;
    padding: clamp(1rem, 3vh, 3rem);
  }

  .modal {
    background: var(--bg-panel);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    width: min(90vw, 900px);
    max-height: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: clamp(0.9rem, 1.8vh, 1.4rem) clamp(1rem, 2vw, 1.75rem);
    border-bottom: 1px solid var(--border-color);
  }

  .modal-header h1 {
    margin: 0;
    font-size: var(--font-group-header);
    color: var(--text-primary);
  }

  .icon-button {
    background: transparent;
    border: none;
    color: var(--text-secondary);
    font-size: 1.3rem;
    line-height: 1;
    padding: 0.25rem 0.5rem;
  }

  .modal-body {
    overflow-y: auto;
    padding: clamp(1rem, 2vh, 1.75rem);
    display: flex;
    flex-direction: column;
    gap: clamp(1.25rem, 2.5vh, 2rem);
  }

  section h2 {
    margin: 0 0 clamp(0.6rem, 1.2vh, 1rem);
    font-size: var(--font-nav-item);
    color: var(--text-primary);
  }

  .scan-form {
    display: flex;
    flex-wrap: wrap;
    align-items: end;
    gap: clamp(0.6rem, 1.2vw, 1rem);
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
    font-size: var(--font-toggle);
    color: var(--text-secondary);
  }

  .port-field {
    width: 7rem;
  }

  input,
  select {
    font-size: var(--font-toggle);
    padding: clamp(0.45rem, 0.9vh, 0.65rem);
    border-radius: var(--radius);
    border: 1px solid var(--border-color);
    background: var(--bg-app);
    color: var(--text-primary);
  }

  button {
    font-size: var(--font-toggle);
    border-radius: var(--radius);
    border: none;
    padding: clamp(0.45rem, 0.9vh, 0.65rem) clamp(0.9rem, 1.6vw, 1.4rem);
  }

  button:disabled {
    opacity: 0.5;
    cursor: default;
  }

  button.primary {
    background: var(--accent);
    color: var(--bg-app);
    font-weight: 600;
  }

  button.secondary {
    background: var(--bg-app);
    color: var(--text-primary);
    border: 1px solid var(--border-color);
  }

  .in-progress,
  .hint {
    margin: clamp(0.5rem, 1vh, 0.85rem) 0;
    color: var(--text-secondary);
    font-size: var(--font-toggle);
  }

  .error {
    margin: clamp(0.5rem, 1vh, 0.85rem) 0;
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

  .device-list {
    list-style: none;
    margin: 0 0 clamp(0.6rem, 1.2vh, 1rem);
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    max-height: 40vh;
    overflow-y: auto;
  }

  .device {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: clamp(0.45rem, 0.9vh, 0.65rem) clamp(0.6rem, 1vw, 0.85rem);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    background: var(--bg-app);
    font-size: var(--font-toggle);
  }

  .device-ip {
    font-family: ui-monospace, Consolas, monospace;
    color: var(--text-primary);
    min-width: 11ch;
  }

  .device-name {
    color: var(--text-secondary);
  }

  .create-form {
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    padding: clamp(0.9rem, 1.8vh, 1.4rem);
    margin-bottom: clamp(1rem, 2vh, 1.5rem);
    display: flex;
    flex-direction: column;
    gap: clamp(0.6rem, 1.2vh, 0.9rem);
  }

  .create-form h3 {
    margin: 0;
    font-size: var(--font-toggle);
    color: var(--text-primary);
  }

  .priority-list ol {
    list-style: none;
    margin: 0;
    padding: 0;
    counter-reset: priority;
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
  }

  .priority-list li {
    counter-increment: priority;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    padding: clamp(0.4rem, 0.8vh, 0.6rem) clamp(0.6rem, 1vw, 0.85rem);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    background: var(--bg-app);
  }

  .priority-list li::before {
    content: counter(priority) '.';
    font-weight: 600;
    color: var(--text-secondary);
    margin-right: 0.5rem;
  }

  .priority-ip {
    font-family: ui-monospace, Consolas, monospace;
    color: var(--text-primary);
    flex: 1;
  }

  .priority-buttons {
    display: flex;
    gap: 0.4rem;
  }

  .priority-buttons button {
    padding: 0.3rem 0.6rem;
    font-size: calc(var(--font-toggle) * 0.85);
    background: var(--bg-panel);
    color: var(--text-primary);
    border: 1px solid var(--border-color);
  }

  .form-actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.6rem;
  }

  .groups-panel {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: clamp(0.75rem, 1.5vw, 1.25rem);
  }

  .group-card {
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    padding: clamp(0.75rem, 1.5vh, 1.1rem);
    background: var(--bg-app);
  }

  .group-card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    margin-bottom: 0.5rem;
  }

  .group-card-header h3 {
    margin: 0;
    font-size: var(--font-toggle);
    color: var(--text-primary);
  }

  .group-type {
    color: var(--text-secondary);
    font-weight: 400;
  }

  .group-card-header button {
    padding: 0.3rem 0.7rem;
    font-size: calc(var(--font-toggle) * 0.85);
  }

  .group-ips {
    list-style: none;
    counter-reset: gip;
    margin: 0;
    padding: 0;
    font-family: ui-monospace, Consolas, monospace;
    font-size: calc(var(--font-toggle) * 0.9);
    color: var(--text-secondary);
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
  }

  .group-ips li {
    counter-increment: gip;
  }

  .group-ips li::before {
    content: counter(gip) '. ';
  }

  .modal-footer {
    border-top: 1px solid var(--border-color);
    padding: clamp(0.9rem, 1.8vh, 1.4rem) clamp(1rem, 2vw, 1.75rem);
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: clamp(0.75rem, 1.5vw, 1.25rem);
  }

  .confirm-overlay {
    z-index: 200;
  }

  .confirm-dialog {
    width: min(90vw, 460px);
    padding: clamp(1.25rem, 2.5vh, 1.75rem);
    gap: clamp(0.75rem, 1.5vh, 1.1rem);
  }

  .confirm-dialog h2 {
    margin: 0;
    font-size: var(--font-nav-item);
    color: var(--text-primary);
  }

  .confirm-dialog p {
    margin: 0;
    color: var(--text-secondary);
    font-size: var(--font-toggle);
  }

  .confirm-dialog .form-actions {
    margin-top: 0.25rem;
  }

  button.primary.danger {
    background: var(--danger-bg);
    color: var(--danger-fg);
  }
</style>
