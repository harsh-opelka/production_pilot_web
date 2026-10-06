<script>
  // Service-only. Lets a technician mirror the physical floor: drag each
  // machine group (and any TVs) to where it stands, choose row/column per
  // group, then Save — the dashboard's tile view renders the same layout
  // (see Dashboard.svelte). The canvas is a scaled-down 1080p TV tile
  // area and every block is drawn at its TRUE size relative to it
  // (floorLayout.naturalGroupSize), so overlaps seen here are real. Reset
  // to default clears the saved layout (dashboard goes back to stacked).
  import { onMount } from 'svelte';
  import { lang, machinesState, floorLayout } from './stores.js';
  import { translate } from './translations.js';
  import { getLayout, saveLayout, ServiceApiError } from './serviceApi.js';
  import {
    REFERENCE_AREA,
    REFERENCE_VIEWPORT,
    SNAP_PCT,
    TV_SIZE_PX,
    clamp,
    defaultPositions,
    findOverlaps,
    naturalGroupSize,
    naturalTileSize,
    snap,
  } from './floorLayout.js';
  import TvIcon from './TvIcon.svelte';

  let savedGroups = $state({}); // what's on the server (for the "not placed yet" hint)
  let positions = $state({}); // group name -> { x, y, orientation } — edited, not yet saved
  let tvs = $state([]); // [{ x, y }]
  let loaded = $state(false);
  let dirty = $state(false);
  let busy = $state(false);
  let message = $state('');
  let error = $state('');

  let canvasEl = $state();
  let canvasW = $state(0);

  // Live groups (config order) — names, PLC counts and machine numbers.
  let groups = $derived($machinesState.groups);
  // Groups without an edited/saved position get a default stacked spot.
  let shown = $derived({ ...defaultPositions(groups, positions), ...positions });

  // Reference-TV px -> percent of the reference tile area.
  const pctW = (px) => (px / REFERENCE_AREA.w) * 100;
  const pctH = (px) => (px / REFERENCE_AREA.h) * 100;

  // Mini-preview metrics: the reference TV's real header/gap/tile sizes,
  // scaled to this canvas.
  const REF_TILE = naturalTileSize(REFERENCE_VIEWPORT.w, REFERENCE_VIEWPORT.h);
  const REF_HEADER = naturalGroupSize(1, 'horizontal').h - REF_TILE.h;
  let scale = $derived(canvasW / REFERENCE_AREA.w);

  function tvSize() {
    return { w: pctW(TV_SIZE_PX.w), h: pctH(TV_SIZE_PX.h) };
  }

  // Same shift-back rule as the dashboard (floorLayout.placeInArea): an
  // item stays fully inside; one bigger than the area is pinned to 0.
  function clampPosition(x, y, size) {
    return { x: clamp(x, 0, Math.max(0, 100 - size.w)), y: clamp(y, 0, Math.max(0, 100 - size.h)) };
  }

  // Warnings at REAL size: blocks overlapping each other (or a TV), and
  // blocks simply bigger than the screen.
  let rects = $derived([
    ...groups.map((g) => {
      const p = shown[g.name];
      const size = blockSize(g.name, p.orientation);
      return { label: g.name, left: p.x, top: p.y, w: size.w, h: size.h };
    }),
    ...tvs.map((tv, i) => ({ label: `${translate($lang, 'service_layout_tv')} ${i + 1}`, left: tv.x, top: tv.y, ...tvSize() })),
  ]);
  let overlaps = $derived(loaded ? findOverlaps(rects) : []);
  let tooBig = $derived(loaded ? rects.filter((r) => r.w > 100 || r.h > 100).map((r) => r.label) : []);

  function apply(layout) {
    savedGroups = { ...layout.groups };
    positions = { ...layout.groups };
    tvs = layout.tvs.map((tv) => ({ ...tv }));
    dirty = false;
  }

  onMount(async () => {
    try {
      apply(await getLayout());
    } catch (err) {
      error = err instanceof ServiceApiError ? err.message : String(err);
    } finally {
      loaded = true;
    }
  });

  function blockSize(name, orientation) {
    const group = groups.find((g) => g.name === name);
    const size = naturalGroupSize(group ? group.plcs.length : 1, orientation);
    return { w: pctW(size.w), h: pctH(size.h) };
  }

  function place(kind, key, x, y) {
    if (kind === 'group') {
      const current = shown[key];
      positions = { ...positions, [key]: { ...current, ...clampPosition(x, y, blockSize(key, current.orientation)) } };
    } else {
      tvs = tvs.map((tv, i) => (i === key ? clampPosition(x, y, tvSize()) : tv));
    }
    dirty = true;
    message = '';
  }

  // --- Dragging (pointer events; works for mouse and touch) ----------------
  let drag = null;

  function startDrag(event, kind, key) {
    if (event.button !== 0 || !canvasEl) return;
    const origin = kind === 'group' ? shown[key] : tvs[key];
    drag = {
      kind,
      key,
      rect: canvasEl.getBoundingClientRect(),
      startX: event.clientX,
      startY: event.clientY,
      x: origin.x,
      y: origin.y,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
    event.preventDefault();
  }

  function moveDrag(event) {
    if (!drag) return;
    const dx = ((event.clientX - drag.startX) / drag.rect.width) * 100;
    const dy = ((event.clientY - drag.startY) / drag.rect.height) * 100;
    place(drag.kind, drag.key, snap(drag.x + dx), snap(drag.y + dy));
  }

  function endDrag() {
    drag = null;
  }

  // Arrow keys nudge the focused item by one grid step.
  const NUDGE = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };

  function nudge(event, kind, key) {
    const step = NUDGE[event.key];
    if (!step) return;
    event.preventDefault();
    const current = kind === 'group' ? shown[key] : tvs[key];
    place(kind, key, snap(current.x) + step[0] * SNAP_PCT, snap(current.y) + step[1] * SNAP_PCT);
  }

  function setOrientation(name, orientation) {
    const current = shown[name];
    positions = { ...positions, [name]: { ...clampPosition(current.x, current.y, blockSize(name, orientation)), orientation } };
    dirty = true;
    message = '';
  }

  function addTv() {
    const size = tvSize();
    tvs = [...tvs, clampPosition(snap(50 - size.w / 2), SNAP_PCT, size)];
    dirty = true;
    message = '';
  }

  function removeTv(index) {
    tvs = tvs.filter((_, i) => i !== index);
    dirty = true;
    message = '';
  }

  const round = (value) => Math.round(value * 100) / 100;

  async function persist(layout, doneKey) {
    busy = true;
    error = '';
    message = '';
    try {
      const result = await saveLayout(layout);
      apply(result);
      floorLayout.set(result);
      message = translate($lang, doneKey);
    } catch (err) {
      error = translate($lang, 'service_layout_error', {
        error: err instanceof ServiceApiError ? err.message : String(err),
      });
    } finally {
      busy = false;
    }
  }

  function save() {
    const layoutGroups = {};
    for (const group of groups) {
      const p = shown[group.name];
      layoutGroups[group.name] = { x: round(p.x), y: round(p.y), orientation: p.orientation };
    }
    persist({ groups: layoutGroups, tvs: tvs.map((tv) => ({ x: round(tv.x), y: round(tv.y) })) }, 'service_layout_saved');
  }

  function reset() {
    persist({ groups: {}, tvs: [] }, 'service_layout_reset_done');
  }

  const sortedPlcs = (group) => [...group.plcs].sort((a, b) => a.unit_number - b.unit_number);
</script>

<h2>{translate($lang, 'service_layout_heading')}</h2>
<p class="desc">{translate($lang, 'service_layout_desc')}</p>

{#if groups.length === 0}
  <p class="desc">{translate($lang, 'service_layout_no_groups')}</p>
{:else}
  <div
    class="canvas"
    bind:this={canvasEl}
    bind:clientWidth={canvasW}
    style="aspect-ratio: {REFERENCE_AREA.w} / {REFERENCE_AREA.h}; --ed-gap: {REF_TILE.gap * scale}px; --ed-header: {REF_HEADER * scale}px; --ed-font-header: {REF_HEADER * scale * 0.45}px; --ed-font-unit: {REF_TILE.h * scale * 0.3}px;"
  >
    {#if loaded}
      {#each tvs as tv, i (i)}
        {@const size = tvSize()}
        <div
          class="item tv"
          role="button"
          tabindex="0"
          aria-label={translate($lang, 'service_layout_tv')}
          style="left: {tv.x}%; top: {tv.y}%; width: {size.w}%; height: {size.h}%;"
          onpointerdown={(e) => startDrag(e, 'tv', i)}
          onpointermove={moveDrag}
          onpointerup={endDrag}
          onpointercancel={endDrag}
          onkeydown={(e) => nudge(e, 'tv', i)}
        >
          <TvIcon title={translate($lang, 'service_layout_tv')} />
          <button
            type="button"
            class="remove-tv"
            aria-label={translate($lang, 'service_layout_remove_tv')}
            title={translate($lang, 'service_layout_remove_tv')}
            onpointerdown={(e) => e.stopPropagation()}
            onclick={() => removeTv(i)}>×</button
          >
        </div>
      {/each}

      {#each groups as group (group.name)}
        {@const p = shown[group.name]}
        {@const size = blockSize(group.name, p.orientation)}
        <div
          class="item group"
          class:unplaced={!savedGroups[group.name]}
          role="button"
          tabindex="0"
          aria-label={group.name}
          style="left: {p.x}%; top: {p.y}%; width: {size.w}%; height: {size.h}%;"
          onpointerdown={(e) => startDrag(e, 'group', group.name)}
          onpointermove={moveDrag}
          onpointerup={endDrag}
          onpointercancel={endDrag}
          onkeydown={(e) => nudge(e, 'group', group.name)}
        >
          <div class="group-name">{group.name}</div>
          <div class="mini-tiles" class:vertical={p.orientation === 'vertical'}>
            {#each sortedPlcs(group) as plc (plc.ip)}
              <div class="mini-tile">{plc.unit_number}</div>
            {/each}
          </div>
        </div>
      {/each}
    {/if}
  </div>

  {#if overlaps.length || tooBig.length}
    <div class="warning" role="status">
      {#each overlaps as [a, b] (`${a}|${b}`)}
        <p>⚠ {translate($lang, 'service_layout_overlap', { a, b })}</p>
      {/each}
      {#each tooBig as name (name)}
        <p>⚠ {translate($lang, 'service_layout_too_big', { group: name })}</p>
      {/each}
    </div>
  {/if}

  <div class="group-options">
    {#each groups as group (group.name)}
      {@const orientation = shown[group.name]?.orientation ?? 'horizontal'}
      <div class="group-option">
        <span class="option-name">
          {group.name}
          {#if loaded && !savedGroups[group.name]}
            <span class="hint">({translate($lang, 'service_layout_not_placed')})</span>
          {/if}
        </span>
        <div
          class="segmented"
          role="radiogroup"
          aria-label={translate($lang, 'service_layout_orientation', { group: group.name })}
        >
          <button
            type="button"
            class:active={orientation === 'horizontal'}
            onclick={() => setOrientation(group.name, 'horizontal')}
          >
            {translate($lang, 'service_layout_horizontal')}
          </button>
          <button
            type="button"
            class:active={orientation === 'vertical'}
            onclick={() => setOrientation(group.name, 'vertical')}
          >
            {translate($lang, 'service_layout_vertical')}
          </button>
        </div>
      </div>
    {/each}
  </div>

  <div class="actions">
    <button type="button" class="secondary" disabled={!loaded || busy} onclick={addTv}>
      + {translate($lang, 'service_layout_add_tv')}
    </button>
    <span class="spacer"></span>
    {#if dirty}
      <span class="hint">{translate($lang, 'service_layout_unsaved')}</span>
    {/if}
    <button type="button" class="secondary" disabled={!loaded || busy} onclick={reset}>
      {translate($lang, 'service_layout_reset')}
    </button>
    <button type="button" class="primary" disabled={!loaded || busy} onclick={save}>
      {translate($lang, 'service_save')}
    </button>
  </div>
{/if}

{#if error}
  <p class="error">{error}</p>
{:else if message}
  <p class="message">{message}</p>
{/if}

<style>
  h2 {
    margin: 0 0 0.5rem;
    font-size: var(--font-group-header);
    color: var(--text-primary);
  }

  .desc {
    margin: 0 0 clamp(0.75rem, 1.5vh, 1.1rem);
    color: var(--text-secondary);
    font-size: var(--font-toggle);
  }

  /* The reference TV's tile area (aspect ratio set inline), scaled down,
     with a light 10 % guide grid (items snap to 2 %). */
  .canvas {
    position: relative;
    width: 100%;
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    background-color: var(--bg-app);
    background-image:
      linear-gradient(to right, var(--border-color) 1px, transparent 1px),
      linear-gradient(to bottom, var(--border-color) 1px, transparent 1px);
    background-size: 10% 10%;
    overflow: hidden;
    touch-action: none;
  }

  .item {
    position: absolute;
    cursor: grab;
    user-select: none;
  }

  .item:active {
    cursor: grabbing;
  }

  .item:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  /* Outline drawn outside (box-shadow), so the block's box is exactly the
     group's real footprint. */
  .group {
    display: flex;
    flex-direction: column;
    background: color-mix(in srgb, var(--bg-panel) 85%, transparent);
    box-shadow:
      0 0 0 2px var(--accent),
      0 2px 8px rgba(0, 0, 0, 0.25);
    border-radius: 0.3rem;
  }

  .group.unplaced {
    box-shadow: none;
    outline: 2px dashed var(--text-secondary);
  }

  .group-name {
    height: var(--ed-header);
    line-height: var(--ed-header);
    font-size: var(--ed-font-header);
    font-weight: 700;
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .mini-tiles {
    flex: 1;
    display: flex;
    gap: var(--ed-gap);
  }

  .mini-tiles.vertical {
    flex-direction: column;
  }

  .mini-tile {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 0.3rem;
    background: var(--state-waiting);
    color: var(--state-waiting-fg);
    font-size: var(--ed-font-unit);
    font-weight: 800;
  }

  .tv {
    color: var(--text-secondary);
  }

  .remove-tv {
    position: absolute;
    top: -0.55rem;
    right: -0.55rem;
    width: 1.3rem;
    height: 1.3rem;
    padding: 0;
    border: none;
    border-radius: 50%;
    background: var(--danger-bg);
    color: var(--danger-fg);
    font-size: 0.9rem;
    line-height: 1.3rem;
  }

  .warning {
    margin-top: 0.6rem;
    padding: 0.5rem 0.8rem;
    border-radius: var(--radius);
    border: 1px solid var(--state-heating);
    background: color-mix(in srgb, var(--state-heating) 15%, transparent);
    color: var(--text-primary);
    font-size: var(--font-toggle);
  }

  .warning p {
    margin: 0.15rem 0;
  }

  .group-options {
    display: flex;
    flex-wrap: wrap;
    gap: 0.6rem 1.5rem;
    margin-top: clamp(0.75rem, 1.5vh, 1.1rem);
  }

  .group-option {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    font-size: var(--font-toggle);
    color: var(--text-primary);
  }

  .option-name {
    font-weight: 600;
  }

  .hint {
    color: var(--text-secondary);
    font-weight: 400;
    font-size: calc(var(--font-toggle) * 0.9);
  }

  .segmented {
    display: inline-flex;
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    overflow: hidden;
  }

  .segmented button {
    font-size: calc(var(--font-toggle) * 0.9);
    padding: 0.3rem 0.8rem;
    border: none;
    background: var(--bg-app);
    color: var(--text-secondary);
  }

  .segmented button.active {
    background: var(--accent);
    color: var(--opelka-blue-fg);
  }

  .actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.6rem;
    margin-top: clamp(0.75rem, 1.5vh, 1.1rem);
  }

  .spacer {
    flex: 1;
  }

  .actions button {
    font-size: var(--font-toggle);
    font-weight: 600;
    padding: clamp(0.45rem, 0.9vh, 0.7rem) clamp(0.9rem, 1.6vw, 1.4rem);
    border-radius: var(--radius);
    border: 1px solid var(--border-color);
  }

  .actions .primary {
    background: var(--accent);
    border-color: var(--accent);
    color: var(--opelka-blue-fg);
  }

  .actions .secondary {
    background: var(--bg-app);
    color: var(--text-primary);
  }

  .actions button:disabled {
    opacity: 0.6;
    cursor: default;
  }

  .error {
    margin: 0.75rem 0 0;
    color: var(--danger-bg);
    font-weight: 600;
    font-size: var(--font-toggle);
  }

  .message {
    margin: 0.75rem 0 0;
    color: var(--text-secondary);
    font-size: var(--font-toggle);
  }
</style>
