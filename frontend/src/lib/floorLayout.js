// Floor layout geometry, shared by the dashboard (Dashboard.svelte) and the
// Service editor (FloorLayoutEditor.svelte). See production_pilot/layout.py
// for the stored shape: per group / TV a top-left position as a PERCENT of
// the dashboard's tile area (x of its width, y of its height).
//
// The layout only decides WHERE things sit — it never scales them. Tiles,
// groups and TV icons always render at their natural size (the same CSS
// as the stacked view). An item that would run past the right/bottom edge
// at its position is shifted back so it stays visible (placeInArea).
//
// The dashboard measures real rendered sizes. The editor can't (it runs on
// a laptop, not the TV), so it computes them for a reference TV with the
// same CSS clamp() formulas — keep naturalTileSize/naturalGroupSize in
// step with FryerTile.svelte / MachineGroupSection.svelte.

export const SNAP_PCT = 2;

/** The screen the editor previews: a 1080p TV at Display Size 100 %. */
export const REFERENCE_VIEWPORT = { w: 1920, h: 1080 };
/** Dashboard tile area (.groups) on that screen, in px — measured on the
 *  real page at 1920x1080 (top bar, legend row and footer subtracted). */
export const REFERENCE_AREA = { w: 1856, h: 809 };

/** Fixed, readable TV icon size (6rem x 4.5rem) — Dashboard.svelte's .tv. */
export const TV_SIZE_PX = { w: 96, h: 72 };

const REM = 16;
const clampPx = (min, preferred, max) => Math.min(Math.max(preferred, min), max);

/** Tile width in the STACKED view: its grid is
 *  repeat(auto-fill, minmax(minW, 1fr)) across the tile area, so columns
 *  stretch beyond the minimum to fill the row. The floor layout uses this
 *  same width so tiles are exactly the size they are when stacked. */
export function stackedTileWidth(areaW, minW, gap) {
  const columns = Math.max(1, Math.floor((areaW + gap) / (minW + gap)));
  return Math.max(minW, (areaW - (columns - 1) * gap) / columns);
}

/** Natural tile size (FryerTile.svelte) and gap (MachineGroupSection) on a
 *  vw x vh screen whose tile area is areaW wide. */
export function naturalTileSize(vw, vh, areaW = REFERENCE_AREA.w) {
  const minW = clampPx(11.25 * REM, 0.15 * vw, 15 * REM);
  const gap = clampPx(0.75 * REM, 0.012 * vw, 1.5 * REM);
  return {
    w: stackedTileWidth(areaW, minW, gap),
    h: clampPx(13.75 * REM, 0.22 * vh, 16.25 * REM),
    gap,
  };
}

// MachineGroupSection.svelte: .group-header (font, line-height 1.2,
// margin-bottom) plus the tile row's padding-top that keeps the NEXT badge
// clear of the title.
const HEADER_LINE_HEIGHT = 1.2;
const TILE_ROW_PAD_TOP = 0.6 * REM;

/** Natural { w, h } px of a group block with `count` tiles. */
export function naturalGroupSize(count, orientation, vw = REFERENCE_VIEWPORT.w, vh = REFERENCE_VIEWPORT.h) {
  const n = Math.max(1, count);
  const tile = naturalTileSize(vw, vh);
  const header =
    clampPx(1.2 * REM, 0.017 * vw, 1.9 * REM) * HEADER_LINE_HEIGHT +
    clampPx(1.25 * REM, 0.0275 * vh, 2.25 * REM) +
    TILE_ROW_PAD_TOP;
  const along = (size) => n * size + (n - 1) * tile.gap;
  return orientation === 'vertical'
    ? { w: tile.w, h: header + along(tile.h) }
    : { w: along(tile.w), h: header + tile.h };
}

export function snap(value) {
  return Math.round(value / SNAP_PCT) * SNAP_PCT;
}

export function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

/** Top-left px of an item of size w x h anchored at (xPct, yPct) of an
 *  areaW x areaH area — shifted back (never shrunk) so it stays fully
 *  visible; pinned to 0 if it's simply bigger than the area. */
export function placeInArea(xPct, yPct, w, h, areaW, areaH) {
  return {
    left: clamp((xPct / 100) * areaW, 0, Math.max(0, areaW - w)),
    top: clamp((yPct / 100) * areaH, 0, Math.max(0, areaH - h)),
  };
}

/** Pairs of labels whose rects ({ label, left, top, w, h }) overlap. */
export function findOverlaps(rects) {
  const pairs = [];
  for (let i = 0; i < rects.length; i++) {
    for (let j = i + 1; j < rects.length; j++) {
      const a = rects[i];
      const b = rects[j];
      if (a.left < b.left + b.w && b.left < a.left + a.w && a.top < b.top + b.h && b.top < a.top + a.h) {
        pairs.push([a.label, b.label]);
      }
    }
  }
  return pairs;
}

/** Default spots (percent) for groups with no saved entry yet (editor
 *  only): stacked top-down from the top-left of the reference area,
 *  wrapping into a new column. */
export function defaultPositions(groups, taken = {}) {
  const positions = {};
  let x = 0;
  let y = 0;
  let columnW = 0;
  for (const group of groups) {
    if (taken[group.name]) continue;
    const size = naturalGroupSize(group.plcs.length, 'horizontal');
    const h = (size.h / REFERENCE_AREA.h) * 100;
    const w = (size.w / REFERENCE_AREA.w) * 100;
    if (y + h > 100 && y > 0) {
      x = snap(x + columnW + SNAP_PCT);
      y = 0;
      columnW = 0;
    }
    positions[group.name] = { x, y, orientation: 'horizontal' };
    y = snap(y + h + SNAP_PCT);
    columnW = Math.max(columnW, w);
  }
  return positions;
}
