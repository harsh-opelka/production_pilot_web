<script>
  // Block-view only — the list view is a table (see MachineGroupSection.svelte
  // + MachineListRow.svelte), not a mode of this tile.
  import {
    BLANK,
    formatDuration,
    formatRecipe,
    formatTemperature,
    formatUnitNumber,
    heatingFillLevel,
    stateLabel,
  } from './format.js';
  import { nowTick } from './stores.js';
  import { translate } from './translations.js';

  // isNext/tier: whether this tile is the single machine the Next Action
  // banner currently points at, and which tier drove that pick (see
  // TopBar.svelte + nextAction.js — this never recomputes priority itself,
  // just mirrors the backend's next_action the caller already has). tier
  // is only meaningful when isNext is true.
  let { plc, language = 'en', isNext = false, tier = null } = $props();

  // "Fast fertig"/"Almost finished" override: its own purple token
  // (--state-near-completion) — see app.css. MachineState itself stays BAKING (see
  // production_pilot/priority.py's is_near_completion).
  let stateKey = $derived(plc.near_completion ? 'near-completion' : plc.state.toLowerCase());
  let label = $derived(stateLabel(plc, language));
  let unitLabel = $derived(formatUnitNumber(plc.unit_number));
  let showRemaining = $derived(plc.is_online && plc.state === 'BAKING' && plc.remaining_seconds != null);
  let remainingText = $derived(showRemaining ? formatDuration(plc.remaining_seconds, language) : '');

  // Live elapsed-state timer for the non-baking, non-offline states —
  // ticks off the shared nowTick clock rather than its own interval, and
  // is derived from the server's state_entered_at so a reload resumes
  // from the true elapsed value instead of zero.
  const TIMER_STATES = new Set(['COLD', 'HEATING', 'HOT', 'STANDBY', 'WAITING', 'BLOCKED', 'ERROR', 'UNRECOGNIZED']);
  let showElapsed = $derived(!showRemaining && plc.is_online && TIMER_STATES.has(plc.state) && plc.state_entered_at != null);
  let elapsedText = $derived(showElapsed ? formatDuration(($nowTick - Date.parse(plc.state_entered_at)) / 1000, language) : '');

  let tileStyle = $derived(
    !plc.is_online
      ? ''
      : fillLevel != null
        ? // Heating with a known level: neutral "empty" tile, orange fill below.
          '--tile-bg: var(--heating-empty-bg); --tile-fg: var(--state-heating-fg);'
        : `--tile-bg: var(--state-${stateKey}); --tile-fg: var(--state-${stateKey}-fg);`,
  );
  // Only meaningful (and only applied) while isNext is true — see .tile.next-priority.tier-* below.
  let tierClass = $derived(isNext && tier ? `tier-${tier}` : '');

  // Blank ("—") rather than stale or invented values while offline.
  let recipeText = $derived(plc.is_online ? formatRecipe(plc.recipe_name) : formatRecipe(null));
  let temperatureText = $derived(
    plc.is_online ? formatTemperature(plc.oil_temp_current, plc.oil_temp_target) : formatTemperature(null, null),
  );

  // Hot/Cold are decided by the oil temperature (backend, see
  // production_pilot/hot_cold.py), so on those two tiles the CURRENT
  // temperature is the headline: shown big, the target small beside it.
  let emphasizeCurrent = $derived(
    plc.is_online && (plc.state === 'HOT' || plc.state === 'COLD') && plc.oil_temp_current != null,
  );
  let targetText = $derived(plc.oil_temp_target != null ? String(Math.round(plc.oil_temp_target)) : BLANK);

  // Heating only: a rising "oil level" behind the text (null = no fill —
  // then the tile stays the plain solid Heating orange; see tileStyle).
  let fillLevel = $derived(
    plc.is_online && plc.state === 'HEATING' ? heatingFillLevel(plc.oil_temp_current, plc.oil_temp_target) : null,
  );
</script>

<div
  class="tile {tierClass}"
  class:offline={!plc.is_online}
  class:blocked={plc.is_online && plc.state === 'BLOCKED'}
  class:light-border={plc.is_online && (plc.state === 'STANDBY' || plc.state === 'UNRECOGNIZED')}
  class:heating-level={fillLevel != null}
  class:next-priority={isNext}
  style={tileStyle}
>
  {#if fillLevel != null}
    <!-- Own clipping box (not overflow:hidden on .tile, which would clip
         the NEXT badge sticking out of the corner). -->
    <div class="fill-clip" aria-hidden="true">
      <div class="fill" style="height: {fillLevel * 100}%;"></div>
    </div>
  {/if}
  {#if isNext}
    <div class="next-badge">{translate(language, 'tile_next_badge')}</div>
  {/if}
  <div class="unit">{unitLabel}</div>
  <div class="middle">
    <div class="state">{label}</div>
    {#if showRemaining}
      <div class="time">{remainingText}</div>
    {:else if showElapsed}
      <div class="time">{elapsedText}</div>
    {/if}
  </div>
  <div class="details">
    <div class="recipe" title={recipeText}>{recipeText}</div>
    {#if emphasizeCurrent}
      <div class="temperature emphasized">
        <span class="temp-current">{Math.round(plc.oil_temp_current)} °C</span>
        <span class="temp-target">/ {targetText} °C</span>
      </div>
    {:else}
      <div class="temperature">{temperatureText}</div>
    {/if}
  </div>
</div>

<style>
  /* Grid rows (not a single centered flex stack): unit pinned to the top,
     recipe + temperature pinned to the bottom, state+time centered in the
     flexible middle row — see .middle. The bottom lines always render
     (as "—" when unknown) so tile height/layout never shift. */
  .tile {
    --tile-bg: var(--offline-bg);
    --tile-fg: var(--offline-fg);
    position: relative;
    background: var(--tile-bg);
    color: var(--tile-fg);
    border-radius: var(--tile-radius);
    /* No visible border on colored state tiles — --tile-shadow (theme-
       dependent, see app.css) provides the separation from --bg-app and
       neighbouring tiles instead: a soft outer drop shadow plus a faint
       inset top-edge highlight ("Option A" subtle depth) — both flat
       box-shadow layers, deliberately no gradient/gloss overlay, so the
       state colour itself stays exactly as flat and solid as before. */
    border: none;
    box-shadow: var(--tile-shadow);
    height: clamp(13.75rem, 22vh, 16.25rem);
    min-width: 0;
    padding: clamp(0.75rem, 1.5vw, 1.5rem);
    display: grid;
    grid-template-rows: auto 1fr auto;
    justify-items: center;
    text-align: center;
  }

  /* Heating with a known oil level: white (light theme) / light slate
     (dark theme) "empty" tile with a thin neutral border, the orange level
     rising inside. Border via inset box-shadow so the tile's box never
     changes size. */
  .tile.heating-level {
    box-shadow:
      var(--tile-shadow),
      inset 0 0 0 1px var(--heating-empty-border);
  }

  /* Blocked: slate with a dashed border, at full opacity — the dashed
     edge says "held up", the solid colour says "online" (unlike the dimmed
     dashed Offline tile below). */
  .tile.blocked {
    border: 2px dashed var(--state-blocked-border);
  }

  /* Standby without a temperature / Unknown: Cold's grey with a lighter
     solid border, so they read apart from a real Cold tile (and from the
     dimmed, dashed Offline tile). Inset, so the tile never changes size. */
  .tile.light-border {
    box-shadow:
      var(--tile-shadow),
      inset 0 0 0 3px var(--state-standby-border);
  }

  .tile.offline {
    background: var(--offline-bg);
    color: var(--offline-fg);
    border: 2px dashed var(--offline-border);
    opacity: 0.5;
  }

  /* Top-priority highlight — the one tile matching the Next Action banner
     (see FryerTile's isNext/tier props + Dashboard.svelte). Coloured
     border + soft halo, using the exact same colour as the banner's
     tier-* background (TopBar.svelte) so the two always agree. Only ever
     one tile at a time carries this, since isNext is derived from the
     single computeNextAction() result the whole dashboard shares. */
  .tile.next-priority {
    border: 3px solid var(--tile-accent, transparent);
    box-shadow:
      var(--tile-shadow),
      0 0 0 6px var(--tile-accent-glow, transparent);
  }

  .tile.next-priority.tier-error {
    --tile-accent: var(--state-error);
    --tile-accent-glow: rgba(220, 38, 38, 0.35);
  }

  .tile.next-priority.tier-near-completion {
    --tile-accent: var(--state-near-completion);
    --tile-accent-glow: rgba(147, 51, 234, 0.4);
  }

  .tile.next-priority.tier-load {
    --tile-accent: var(--state-waiting);
    --tile-accent-glow: rgba(5, 52, 108, 0.35);
  }

  .tile.next-priority.tier-hot {
    --tile-accent: var(--state-hot);
    --tile-accent-fg: var(--state-hot-fg);
    --tile-accent-glow: rgba(250, 204, 21, 0.4);
  }

  /* Cold / plain Standby picked for "Switch to Auto": the tile's own grey,
     the same own-colour ring + soft halo a Waiting tile gets — no yellow. */
  .tile.next-priority.tier-cold {
    --tile-accent: var(--state-cold);
    --tile-accent-fg: var(--state-cold-fg);
    --tile-accent-glow: rgba(107, 114, 128, 0.35);
  }

  /* Text sits above the heating fill (which is absolutely positioned and
     so not a grid row of its own). */
  .unit,
  .middle,
  .details {
    position: relative;
    z-index: 1;
  }

  .fill-clip {
    position: absolute;
    inset: 0;
    border-radius: inherit;
    overflow: hidden;
    pointer-events: none;
  }

  /* Height is set inline from the fill level; the transition makes it
     rise smoothly between ~0.5 s polls instead of jumping. Only height
     changes — the tile's own box never moves or resizes. The top edge is
     a plain straight line. */
  .fill {
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0;
    /* Exactly the legend's Heating orange. */
    background: var(--state-heating);
    transition: height 1.5s ease;
  }

  .next-badge {
    position: absolute;
    top: -0.6rem;
    left: -0.6rem;
    padding: 0.15rem 0.6rem;
    border-radius: 999px;
    background: var(--tile-accent, var(--opelka-blue));
    color: var(--tile-accent-fg, #ffffff);
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.02em;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.35);
    z-index: 1;
  }

  .unit {
    align-self: start;
    font-size: var(--font-tile-unit);
    font-weight: 800;
    line-height: 1;
  }

  .middle {
    align-self: center;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: clamp(0.15rem, 0.4vh, 0.35rem);
  }

  .state {
    font-size: var(--font-tile-state);
    font-weight: 700;
  }

  .time {
    font-size: var(--font-tile-time);
    font-weight: 700;
    font-variant-numeric: tabular-nums;
  }

  .details {
    align-self: end;
    width: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.1em;
    font-size: var(--font-tile-sub);
    line-height: 1.2;
  }

  .recipe {
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-weight: 400;
    opacity: 0.85;
  }

  .temperature {
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }

  .temperature.emphasized {
    display: flex;
    align-items: baseline;
    gap: 0.35em;
  }

  .temp-current {
    font-size: var(--font-tile-time);
    font-weight: 800;
  }

  .temp-target {
    font-weight: 400;
    opacity: 0.85;
  }
</style>
