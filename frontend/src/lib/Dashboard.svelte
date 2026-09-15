<script>
  import { machinesState, view, lang, auth } from './stores.js';
  import { todayLocalDate } from './format.js';
  import { getDailySummary } from './serviceApi.js';
  import { computeNextAction } from './nextAction.js';
  import MachineGroupSection from './MachineGroupSection.svelte';
  import ViewToggle from './ViewToggle.svelte';
  import StateLegend from './StateLegend.svelte';

  // Same computeNextAction() call TopBar.svelte uses for the Next Action
  // banner text/colour — reused here (not re-derived) purely to know which
  // single plc.ip to highlight on the matching tile, see MachineGroupSection.
  let nextAction = $derived(computeNextAction($machinesState.groups, $lang));

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
    <StateLegend language={$lang} />
    <ViewToggle />
  </div>

  <div class="groups">
    {#each $machinesState.groups as group (group.name)}
      <MachineGroupSection
        {group}
        mode={$view}
        language={$lang}
        {productivityByIp}
        nextActionIp={nextAction.ip}
        nextActionTier={nextAction.tier}
      />
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

  /* Legend (see StateLegend.svelte) and the Block/List toggle grouped
     together on the right side of this row, legend first then the
     toggle immediately after it — not spread across the full width.
     wrap so a narrow viewport/high --ui-scale stacks the toggle onto its
     own line under the legend rather than crushing either. */
  .toolbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: flex-end;
    gap: clamp(0.5rem, 1.2vh, 0.85rem) clamp(1rem, 2vw, 2rem);
    margin-bottom: clamp(0.75rem, 1.5vh, 1.5rem);
    flex-shrink: 0;
  }

  .groups {
    flex: 1;
    overflow-y: auto;
  }
</style>
