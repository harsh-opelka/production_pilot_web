<script>
  import { machinesState, view, lang, auth } from './stores.js';
  import { translate } from './translations.js';
  import { todayLocalDate } from './format.js';
  import { getDailySummary } from './serviceApi.js';
  import MachineGroupSection from './MachineGroupSection.svelte';

  const PRODUCTIVITY_REFRESH_MS = 60_000;

  let productivityByIp = $state({});

  async function loadProductivity() {
    // /api/stats/daily-summary is Management-level detail (same gate as
    // the Statistics screen) — an anonymous Dashboard viewer simply gets
    // blank Produktivität cells rather than a failed-request retry loop.
    if (!$auth.token) return;
    try {
      const data = await getDailySummary(todayLocalDate());
      const map = {};
      for (const m of data.machines) map[m.plc_ip] = m.productivity_pct;
      productivityByIp = map;
    } catch {
      // Non-fatal — list view just shows blank Produktivität cells.
    }
  }

  $effect(() => {
    loadProductivity();
    const interval = setInterval(loadProductivity, PRODUCTIVITY_REFRESH_MS);
    return () => clearInterval(interval);
  });
</script>

<div class="dashboard">
  <div class="toolbar">
    <div class="view-toggle" role="group" aria-label="View mode">
      <button class:active={$view === 'block'} onclick={() => view.set('block')}>
        {translate($lang, 'block_view')}
      </button>
      <button class:active={$view === 'list'} onclick={() => view.set('list')}>
        {translate($lang, 'list_view')}
      </button>
    </div>
  </div>

  <div class="groups">
    {#each $machinesState.groups as group (group.name)}
      <MachineGroupSection {group} mode={$view} language={$lang} {productivityByIp} />
    {/each}
  </div>
</div>

<style>
  .dashboard {
    height: 100%;
    display: flex;
    flex-direction: column;
    padding: clamp(0.75rem, 1.5vh, 1.5rem) clamp(1rem, 2vw, 2rem);
    overflow: hidden;
  }

  .toolbar {
    display: flex;
    justify-content: flex-end;
    margin-bottom: clamp(0.75rem, 1.5vh, 1.5rem);
    flex-shrink: 0;
  }

  .view-toggle {
    display: flex;
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    overflow: hidden;
  }

  .view-toggle button {
    font-size: var(--font-view-toggle);
    padding: clamp(0.4rem, 0.7vh, 0.7rem) clamp(0.9rem, 1.4vw, 1.5rem);
    border: none;
    background: var(--bg-panel);
    color: var(--text-secondary);
    transition: background 0.15s, color 0.15s;
  }

  .view-toggle button.active {
    background: var(--opelka-blue);
    color: var(--opelka-blue-fg);
    font-weight: 600;
  }

  .groups {
    flex: 1;
    overflow-y: auto;
  }
</style>
