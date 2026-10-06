<script>
  import { machinesState, view, lang, auth, floorLayout } from './stores.js';
  import { todayLocalDate } from './format.js';
  import { getDailySummary, getLayout } from './serviceApi.js';
  import { describeNextAction } from './nextAction.js';
  import { translate } from './translations.js';
  import { TV_SIZE_PX, placeInArea, stackedTileWidth } from './floorLayout.js';
  import MachineGroupSection from './MachineGroupSection.svelte';
  import ViewToggle from './ViewToggle.svelte';
  import StateLegend from './StateLegend.svelte';
  import TvIcon from './TvIcon.svelte';

  // Same describeNextAction() call TopBar.svelte uses for the Next Action
  // banner text/colour — reused here (not re-derived) purely to know which
  // single plc.ip gets the NEXT badge, see MachineGroupSection.
  let nextAction = $derived(describeNextAction($machinesState.next_action, $lang));

  const PRODUCTIVITY_REFRESH_MS = 60_000;
  // The TV picks up a layout saved from another device within this time.
  const LAYOUT_REFRESH_MS = 30_000;

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

  async function loadLayout() {
    try {
      floorLayout.set(await getLayout());
    } catch {
      // Non-fatal — keep the last known layout (or the stacked fallback).
    }
  }

  $effect(() => {
    loadProductivity();
    const interval = setInterval(loadProductivity, PRODUCTIVITY_REFRESH_MS);
    return () => clearInterval(interval);
  });

  $effect(() => {
    loadLayout();
    const interval = setInterval(loadLayout, LAYOUT_REFRESH_MS);
    return () => clearInterval(interval);
  });

  // Floor layout (tile view only — List View ignores it). A group with a
  // saved entry is drawn with its top-left at its saved (x %, y %) of this
  // tile area, at its NATURAL size (never scaled — see floorLayout.js); a
  // group that would run past the right/bottom edge is shifted back. A
  // group without an entry (no layout saved yet, or created after the last
  // save) falls back to the stacked layout below, so nothing disappears.
  let savedGroups = $derived($floorLayout?.groups ?? {});
  let placedGroups = $derived(
    $view === 'block' ? $machinesState.groups.filter((g) => savedGroups[g.name]) : [],
  );
  let stacked = $derived(
    $view === 'block' ? $machinesState.groups.filter((g) => !savedGroups[g.name]) : $machinesState.groups,
  );
  let savedTvs = $derived($view === 'block' && placedGroups.length ? ($floorLayout?.tvs ?? []) : []);

  let areaW = $state(0);
  let areaH = $state(0);
  // Rendered sizes, measured (bind:offsetWidth/Height) — exact whatever
  // the screen, Display Size or font.
  let widths = $state({});
  let heights = $state({});

  let placed = $derived(
    placedGroups.map((g) => {
      const entry = savedGroups[g.name];
      const w = widths[g.name] ?? 0;
      const h = heights[g.name] ?? 0;
      return { group: g, orientation: entry.orientation, h, ...placeInArea(entry.x, entry.y, w, h, areaW, areaH) };
    }),
  );
  let tvs = $derived(
    savedTvs.map((tv) => placeInArea(tv.x, tv.y, TV_SIZE_PX.w, TV_SIZE_PX.h, areaW, areaH)),
  );
  // The stacked grid's real column width, from the SAME CSS values it uses
  // (min width and gap, read from the rendered page), so floor tiles match.
  let floorEl = $state();
  let floorTileW = $derived.by(() => {
    if (!floorEl || !areaW) return null;
    const probe = getComputedStyle(floorEl);
    const minW = parseFloat(probe.getPropertyValue('--probe-min-w'));
    const gap = parseFloat(probe.getPropertyValue('--probe-gap'));
    return Number.isFinite(minW) && Number.isFinite(gap) ? stackedTileWidth(areaW, minW, gap) : null;
  });

  // Normally the floor just fills the area (CSS height: 100%) — setting
  // it to the measured areaH instead caused a sub-pixel scrollbar loop.
  // Only a block simply bigger than the area (e.g. a vertical QUATTRO on a
  // short screen) gives it an explicit, taller height — then it scrolls.
  let contentBottom = $derived(Math.max(0, ...placed.map((item) => item.top + item.h)));
  let floorH = $derived(contentBottom > areaH + 1 ? contentBottom : null);
</script>

<div class="dashboard">
  <div class="toolbar">
    <StateLegend language={$lang} />
    <ViewToggle />
  </div>

  <div class="groups" bind:clientWidth={areaW} bind:clientHeight={areaH}>
    {#if placed.length}
      <div
        class="floor"
        class:with-stacked={stacked.length > 0}
        bind:this={floorEl}
        style="{floorH ? `height: ${floorH}px;` : ''}{floorTileW ? ` --floor-tile-w: ${floorTileW}px;` : ''}"
      >
        {#each tvs as tv, i (i)}
          <div class="floor-item tv" style="left: {tv.left}px; top: {tv.top}px;">
            <TvIcon title={translate($lang, 'service_layout_tv')} />
          </div>
        {/each}
        {#each placed as item (item.group.name)}
          <div
            class="floor-item"
            style="left: {item.left}px; top: {item.top}px;"
            bind:offsetWidth={widths[item.group.name]}
            bind:offsetHeight={heights[item.group.name]}
          >
            <MachineGroupSection
              group={item.group}
              mode="block"
              language={$lang}
              nextActionIp={nextAction.ip}
              nextActionTier={nextAction.tier}
              floor
              orientation={item.orientation}
            />
          </div>
        {/each}
      </div>
    {/if}

    {#each stacked as group (group.name)}
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
    min-height: 0;
    overflow-x: hidden;
    overflow-y: auto;
  }

  /* The floor: the whole tile area; items are absolutely positioned at
     their natural size (see the placed/tvs derivations above). */
  /* --probe-*: the stacked grid's min column width and gap
     (MachineGroupSection.svelte), resolved to px for floorTileW above.
     Registered as <length> so getComputedStyle returns px, not the clamp(). */
  .floor {
    position: relative;
    width: 100%;
    height: 100%;
    --probe-min-w: clamp(11.25rem, 15vw, 15rem);
    --probe-gap: clamp(0.75rem, 1.2vw, 1.5rem);
  }

  .floor.with-stacked {
    margin-bottom: clamp(1.25rem, 2.5vh, 2.5rem);
  }

  .floor-item {
    position: absolute;
  }

  /* Fixed, readable size — keep in step with floorLayout.TV_SIZE_PX. */
  .floor-item.tv {
    width: 6rem;
    height: 4.5rem;
    color: var(--text-secondary);
  }
</style>
