<script>
  // Word-style colour picker: a swatch button that opens a popover with a
  // "Theme colors" grid (one column per base hue, base on top, lighter
  // tints then darker shades below), a "Standard colors" row, and "More
  // colors…" (saturation/brightness square, hue slider, hex field, old vs
  // new). Built in-app rather than <input type="color">, which looks
  // different on every device and has no shades grid.
  //
  // Floats over the page (absolute, anchored under the swatch — same
  // pattern as the Statistics column picker), closes on a click/tap
  // outside or Esc. Every pick calls onchange(hex) right away; nothing is
  // saved here (see StateColorsCard.svelte).
  import { tick } from 'svelte';
  import { lang } from './stores.js';
  import { translate } from './translations.js';
  import { normalizeHex, hexToRgb, rgbToHex, hexToHsv, hsvToHex } from './stateColors.js';

  let { value, label = '', onchange } = $props();

  // Picker palette (not state colours): base hues incl. OPELKA navy.
  const BASES = [
    '#6B7280', // grey
    '#05346C', // OPELKA navy
    '#2563EB', // blue
    '#0D9488', // teal
    '#16A34A', // green
    '#84CC16', // lime
    '#FACC15', // yellow
    '#F59E0B', // orange
    '#DC2626', // red
    '#9333EA', // purple
  ];
  // Rows under the base: tints towards white, then shades towards black.
  const STEPS = [
    ['white', 0.8],
    ['white', 0.6],
    ['white', 0.4],
    ['black', 0.25],
    ['black', 0.5],
  ];
  const STANDARD = [
    '#C00000', // dark red
    '#FF0000', // red
    '#FFC000', // orange
    '#FFFF00', // yellow
    '#92D050', // light green
    '#00B050', // green
    '#00B0F0', // light blue
    '#0070C0', // blue
    '#002060', // dark blue
    '#7030A0', // purple
  ];
  const COLS = BASES.length;

  function mix(hex, toward, amount) {
    const target = toward === 'white' ? 255 : 0;
    return rgbToHex(hexToRgb(hex).map((c) => c + (target - c) * amount));
  }

  // Rows of cells: 6 theme rows + the standard row — one 2D grid for the
  // arrow keys.
  const rows = [
    BASES,
    ...STEPS.map(([toward, amount]) => BASES.map((b) => mix(b, toward, amount))),
    STANDARD,
  ];
  const THEME_ROWS = rows.length - 1;

  let open = $state(false);
  let more = $state(false);
  let previous = $state(null); // the colour when the popover opened (set in openPicker)
  let focus = $state({ row: 0, col: 0 });
  let rootEl = $state();
  let gridEl = $state();

  async function openPicker() {
    previous = value;
    open = true;
    more = false;
    const hit = findCell(value);
    focus = hit ?? { row: 0, col: 0 };
    syncHsv(value);
    hexDraft = value;
    await tick();
    gridEl?.querySelector(`[data-cell="${focus.row}-${focus.col}"]`)?.focus();
  }

  function close() {
    open = false;
  }

  function findCell(hex) {
    for (let r = 0; r < rows.length; r++) {
      const c = rows[r].indexOf(hex);
      if (c !== -1) return { row: r, col: c };
    }
    return null;
  }

  function pick(hex, closeAfter = false) {
    onchange?.(hex);
    syncHsv(hex);
    hexDraft = hex;
    if (closeAfter) close();
  }

  function onGridKeydown(event) {
    let { row, col } = focus;
    if (event.key === 'ArrowRight') col = Math.min(COLS - 1, col + 1);
    else if (event.key === 'ArrowLeft') col = Math.max(0, col - 1);
    else if (event.key === 'ArrowDown') row = Math.min(rows.length - 1, row + 1);
    else if (event.key === 'ArrowUp') row = Math.max(0, row - 1);
    else if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      pick(rows[row][col], true);
      return;
    } else return;
    event.preventDefault();
    focus = { row, col };
    gridEl.querySelector(`[data-cell="${row}-${col}"]`)?.focus();
  }

  function onWindowPointerdown(event) {
    if (open && rootEl && !rootEl.contains(event.target)) close();
  }

  function onWindowKeydown(event) {
    if (open && event.key === 'Escape') {
      close();
      rootEl?.querySelector('.swatch')?.focus();
    }
  }

  // --- "More colors…": HSV square + hue slider + hex field ---------------
  let hsv = $state({ h: 0, s: 0, v: 0 });
  let hexDraft = $state('');
  let hexError = $state('');

  function syncHsv(hex) {
    const n = normalizeHex(hex);
    if (!n) return;
    const next = hexToHsv(n);
    // Keep the hue when the colour is grey (hue undefined) so the square
    // doesn't jump back to red.
    if (next.s === 0 || next.v === 0) next.h = hsv.h;
    hsv = next;
  }

  function setHsv(next) {
    hsv = next;
    const hex = hsvToHex(next);
    hexDraft = hex;
    hexError = '';
    onchange?.(hex);
  }

  // Pointer drag (mouse, pen and touch alike) with capture, so a drag can
  // leave the element without losing it.
  function drag(event, apply) {
    const el = event.currentTarget;
    el.setPointerCapture(event.pointerId);
    const move = (e) => {
      const rect = el.getBoundingClientRect();
      apply(
        Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width)),
        Math.min(1, Math.max(0, (e.clientY - rect.top) / rect.height)),
      );
    };
    move(event);
    const up = () => {
      el.removeEventListener('pointermove', move);
      el.removeEventListener('pointerup', up);
      el.removeEventListener('pointercancel', up);
    };
    el.addEventListener('pointermove', move);
    el.addEventListener('pointerup', up);
    el.addEventListener('pointercancel', up);
  }

  function onSquareDown(event) {
    drag(event, (x, y) => setHsv({ h: hsv.h, s: x, v: 1 - y }));
  }
  function onSquareKeydown(event) {
    const step = 0.02;
    const moves = { ArrowRight: [step, 0], ArrowLeft: [-step, 0], ArrowUp: [0, step], ArrowDown: [0, -step] };
    const m = moves[event.key];
    if (!m) return;
    event.preventDefault();
    setHsv({ h: hsv.h, s: Math.min(1, Math.max(0, hsv.s + m[0])), v: Math.min(1, Math.max(0, hsv.v + m[1])) });
  }

  function onHueDown(event) {
    drag(event, (x) => setHsv({ ...hsv, h: x * 359.9 }));
  }
  function nudgeHue(delta) {
    setHsv({ ...hsv, h: (((hsv.h + delta) % 360) + 360) % 360 });
  }
  function onHueWheel(event) {
    event.preventDefault();
    nudgeHue(event.deltaY > 0 ? 4 : -4);
  }
  function onHueKeydown(event) {
    const d = { ArrowRight: 2, ArrowUp: 2, ArrowLeft: -2, ArrowDown: -2 }[event.key];
    if (d == null) return;
    event.preventDefault();
    nudgeHue(d);
  }

  function commitHex() {
    const n = normalizeHex(hexDraft);
    if (!n) {
      hexError = translate($lang, 'service_colors_invalid_hex');
      return;
    }
    hexError = '';
    pick(n);
  }
</script>

<svelte:window onpointerdown={onWindowPointerdown} onkeydown={onWindowKeydown} />

<div class="picker-root" bind:this={rootEl}>
  <button
    type="button"
    class="swatch"
    style:background={value}
    aria-label={translate($lang, 'service_colors_pick', { state: label })}
    aria-haspopup="dialog"
    aria-expanded={open}
    onclick={() => (open ? close() : openPicker())}
  ></button>

  {#if open}
    <div class="popover" role="dialog" aria-label={translate($lang, 'service_colors_pick', { state: label })}>
      <div class="grid-label">{translate($lang, 'service_colors_theme')}</div>
      <!-- svelte-ignore a11y_interactive_supports_focus -->
      <div class="grid" role="grid" tabindex="-1" bind:this={gridEl} onkeydown={onGridKeydown}>
        {#each rows as row, r (r)}
          {#if r === THEME_ROWS}
            <div class="grid-label standard-label">{translate($lang, 'service_colors_standard')}</div>
          {/if}
          <div class="grid-row" class:base-row={r === 0} role="row">
            {#each row as hex, c (c)}
              <button
                type="button"
                class="cell"
                class:selected={hex === value}
                role="gridcell"
                data-cell="{r}-{c}"
                tabindex={focus.row === r && focus.col === c ? 0 : -1}
                style:background={hex}
                title={hex}
                aria-label={hex}
                onclick={() => {
                  focus = { row: r, col: c };
                  pick(hex, true);
                }}
              ></button>
            {/each}
          </div>
        {/each}
      </div>

      <button type="button" class="more-toggle" aria-expanded={more} onclick={() => (more = !more)}>
        {translate($lang, 'service_colors_more')}
      </button>

      {#if more}
        <div class="more">
          <div
            class="sv"
            role="slider"
            tabindex="0"
            aria-label={translate($lang, 'service_colors_sv')}
            aria-valuemin="0"
            aria-valuemax="100"
            aria-valuenow={Math.round(hsv.v * 100)}
            aria-valuetext={value}
            style:background-color={hsvToHex({ h: hsv.h, s: 1, v: 1 })}
            onpointerdown={onSquareDown}
            onkeydown={onSquareKeydown}
          >
            <div class="sv-knob" style:left="{hsv.s * 100}%" style:top="{(1 - hsv.v) * 100}%"></div>
          </div>
          <div
            class="hue"
            role="slider"
            tabindex="0"
            aria-label={translate($lang, 'service_colors_hue')}
            aria-valuemin="0"
            aria-valuemax="360"
            aria-valuenow={Math.round(hsv.h)}
            onpointerdown={onHueDown}
            onwheel={onHueWheel}
            onkeydown={onHueKeydown}
          >
            <div class="hue-knob" style:left="{(hsv.h / 360) * 100}%"></div>
          </div>
          <div class="hex-row">
            <input
              class="hex"
              type="text"
              maxlength="9"
              spellcheck="false"
              aria-label={translate($lang, 'service_colors_hex')}
              aria-invalid={hexError ? 'true' : 'false'}
              bind:value={hexDraft}
              onchange={commitHex}
              onpaste={() => setTimeout(commitHex)}
              onkeydown={(e) => e.key === 'Enter' && commitHex()}
            />
            <div class="compare" aria-hidden="true">
              <span class="compare-new" style:background={value} title={translate($lang, 'service_colors_new')}></span>
              <span class="compare-old" style:background={previous} title={translate($lang, 'service_colors_previous')}></span>
            </div>
          </div>
          <div class="compare-labels">
            <span>{translate($lang, 'service_colors_new')}</span>
            <span>{translate($lang, 'service_colors_previous')}</span>
          </div>
          {#if hexError}<div class="error">{hexError}</div>{/if}
        </div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .picker-root {
    position: relative;
    display: inline-flex;
  }

  .swatch {
    width: 2.6rem;
    height: 2.6rem;
    border-radius: 0.45rem;
    border: 2px solid var(--border-color);
    cursor: pointer;
    padding: 0;
  }

  /* Floats over the page (absolute, z-index) — never in the flow. */
  .popover {
    position: absolute;
    top: calc(100% + 0.35rem);
    left: 0;
    z-index: 40;
    width: max-content;
    padding: 0.75rem;
    background: var(--bg-panel);
    color: var(--text-primary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
  }

  .grid-label {
    font-size: 0.8rem;
    font-weight: 600;
    color: var(--text-secondary);
    margin-bottom: 0.35rem;
  }

  .standard-label {
    margin-top: 0.6rem;
  }

  .grid {
    outline: none;
  }

  .grid-row {
    display: grid;
    grid-template-columns: repeat(10, 1.6rem);
    gap: 0.2rem;
  }

  .grid-row + .grid-row {
    margin-top: 0.12rem;
  }

  /* Base colours sit a little apart from their shades, like Word. */
  .grid-row.base-row {
    margin-bottom: 0.3rem;
  }

  .cell {
    width: 1.6rem;
    height: 1.6rem;
    padding: 0;
    border: 1px solid rgba(0, 0, 0, 0.15);
    border-radius: 0.2rem;
    cursor: pointer;
  }

  .cell:hover,
  .cell:focus-visible {
    outline: 2px solid var(--text-primary);
    outline-offset: 1px;
  }

  .cell.selected {
    outline: 2px solid var(--text-primary);
    outline-offset: 1px;
    box-shadow: inset 0 0 0 2px #ffffff;
  }

  .more-toggle {
    margin-top: 0.7rem;
    width: 100%;
    padding: 0.4rem;
    font: inherit;
    font-size: 0.9rem;
    text-align: left;
    background: none;
    color: var(--text-primary);
    border: 1px solid var(--border-color);
    border-radius: 0.35rem;
    cursor: pointer;
  }

  .more {
    margin-top: 0.6rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  /* touch-action: none so a finger drag moves the knob instead of scrolling. */
  .sv {
    position: relative;
    height: 9rem;
    border-radius: 0.35rem;
    background-image: linear-gradient(to top, #000000, transparent), linear-gradient(to right, #ffffff, transparent);
    cursor: crosshair;
    touch-action: none;
  }

  .sv-knob {
    position: absolute;
    width: 0.9rem;
    height: 0.9rem;
    border: 2px solid #ffffff;
    border-radius: 50%;
    box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.6);
    transform: translate(-50%, -50%);
    pointer-events: none;
  }

  .hue {
    position: relative;
    height: 1rem;
    border-radius: 0.5rem;
    background: linear-gradient(to right, #f00, #ff0, #0f0, #0ff, #00f, #f0f, #f00);
    cursor: pointer;
    touch-action: none;
  }

  .hue-knob {
    position: absolute;
    top: 50%;
    width: 0.5rem;
    height: 1.3rem;
    border: 2px solid #ffffff;
    border-radius: 0.25rem;
    box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.6);
    transform: translate(-50%, -50%);
    pointer-events: none;
  }

  .sv:focus-visible,
  .hue:focus-visible {
    outline: 2px solid var(--text-primary);
    outline-offset: 2px;
  }

  .hex-row {
    display: flex;
    align-items: center;
    gap: 0.6rem;
  }

  .hex {
    width: 6.5rem;
    padding: 0.3rem 0.45rem;
    font: inherit;
    font-family: ui-monospace, monospace;
    text-transform: uppercase;
    background: var(--bg-app);
    color: var(--text-primary);
    border: 1px solid var(--border-color);
    border-radius: 0.3rem;
  }

  .compare {
    display: flex;
    border: 1px solid var(--border-color);
    border-radius: 0.3rem;
    overflow: hidden;
  }

  .compare span {
    width: 2.2rem;
    height: 1.6rem;
  }

  .compare-labels {
    display: flex;
    justify-content: flex-end;
    gap: 0.8rem;
    font-size: 0.75rem;
    color: var(--text-secondary);
  }

  .error {
    font-size: 0.8rem;
    color: var(--danger-bg);
  }
</style>
