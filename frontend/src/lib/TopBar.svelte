<script>
  import logo from '../assets/opelka_logo.png';
  import { machinesState, lang, page } from './stores.js';
  import { translate } from './translations.js';
  import { computeNextAction } from './nextAction.js';
  import AuthGate from './AuthGate.svelte';
  import KpiSummary from './KpiSummary.svelte';

  let nextAction = $derived(computeNextAction($machinesState.groups, $lang));
</script>

<header class="topbar">
  <div class="left-group">
    <AuthGate />

    <div class="next-action">
      <div class="next-action-box tier-{nextAction.tier}">
        <span class="na-label">{translate($lang, 'next_action_prefix')}</span>
        <span class="na-content">{nextAction.text}</span>
      </div>
    </div>
  </div>

  <div class="right-group">
    {#if $page === 'dashboard'}
      <KpiSummary />
    {/if}

    <div class="logo-panel">
      <img src={logo} alt="Opelka" />
    </div>
  </div>
</header>

<style>
  .topbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    /* Exactly two top-level flex children now (.left-group, .right-group)
       — with only two items, space-between puts the ENTIRE leftover gap
       in the one place it belongs: between the two groups. Previously
       .next-action sat here as its own direct (3rd) flex child next to
       .right-group; once its flex-grow hit max-width, the leftover space
       space-between had to place got split into TWO gaps (either side of
       it), which visibly dragged the whole block off the left edge
       toward the middle on wide viewports/high --ui-scale — see
       .left-group below for the fix. */
    justify-content: space-between;
    background: var(--bg-topbar);
    border-bottom: 1px solid var(--border-color);
    padding: clamp(0.5rem, 1.2vh, 1rem) clamp(1rem, 2vw, 2rem);
    /* Row-gap (wrap fallback) and column-gap both bumped up from the
       previous clamp(0.5rem, 1vh, 1rem)/clamp(0.75rem, 1.5vw, 1.5rem) —
       gap is a floor space-between adds on top of, not a ceiling, so
       raising it keeps .left-group/.right-group from ever crowding
       together even when there's little leftover space to distribute. */
    gap: clamp(0.75rem, 2vh, 1.5rem) clamp(1.25rem, 2.5vw, 2.5rem);
    flex-shrink: 0;
  }

  /* Hamburger icon + Next Action block as ONE left-anchored unit — see
     .topbar's comment above for why this grouping exists. flex-grow: 1
     (topbar-level) so this still claims the leftover width up to
     .right-group, same as before; the growth is then handed down to
     .next-action's OWN flex-grow (left-group-level) below, so it's
     .next-action that visibly widens while the hamburger stays fixed-size
     right at the left edge — never space distributed around either of
     them. justify-content is deliberately left at its flex-start default:
     any width .next-action's max-width can't absorb just trails as blank
     space after it (still inside/before .right-group), not as a gap
     that would push .next-action away from the hamburger. */
  .left-group {
    flex: 1 1 auto;
    min-width: 0;
    display: flex;
    align-items: center;
    gap: clamp(0.75rem, 1.2vw, 1.25rem);
  }

  /* flex-grow: 1 (relative to .left-group, see above) so this fills the
     leftover space next to the hamburger icon instead of hugging its own
     text — a deliberate reversal of the previous fit-content sizing, now
     that the box needs real presence rather than a small pill. flex-basis
     20rem is just a sane starting point before growth; the generous
     max-width still caps it well short of .right-group so the two never
     collide, and flex-shrink: 1 + na-content's overflow-wrap still let it
     wrap onto its own full-width row (via .topbar's flex-wrap) rather
     than being squeezed to a sliver at high --ui-scale. */
  .next-action {
    flex: 1 1 20rem;
    min-width: 0;
    max-width: clamp(24rem, 46vw, 46rem);
    display: flex;
  }

  /* KPI table + logo as one flex item: at low viewport width / high
     --ui-scale, when this doesn't fit next to .left-group, the whole
     group wraps to its own row together (via .topbar's flex-wrap)
     instead of the KPI table wrapping alone and ending up squeezed
     under Next Action while the logo stays put — see task spec: "KPI
     table should sit clearly to the right side of the bar". The
     explicit gap here is a floor for KPI-to-logo spacing that doesn't
     depend on how much leftover width .topbar's space-between has to
     distribute. */
  .right-group {
    flex: 0 1 auto;
    min-width: 0;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: flex-end;
    gap: clamp(1.25rem, 3vw, 3rem);
  }

  /* Two-tier hierarchy inside one coloured box: a small label on top
     (na-label) and the combined "{unit}: action" text below it in a much
     larger, bold weight (na-content) — see nextAction.js for how that
     text is built. Padding bumped up substantially again from
     clamp(0.55rem, 1.2vh, 0.95rem)/clamp(1rem, 1.9vw, 1.6rem) — the box
     is now much wider AND taller (see .next-action's flex-grow), so it
     needs real breathing room on every side, not just around the text. */
  .next-action-box {
    flex: 1 1 auto;
    min-width: 0;
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: clamp(0.3rem, 0.6vh, 0.6rem);
    padding: clamp(1rem, 2.4vh, 1.9rem) clamp(1.5rem, 3vw, 2.75rem);
    border-radius: var(--radius);
    color: #ffffff;
  }

  .na-label {
    font-size: calc(var(--font-next-action) * 0.38);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    opacity: 0.85;
  }

  .na-content {
    font-size: var(--font-next-action);
    font-weight: 700;
    line-height: 1.15;
    overflow-wrap: break-word;
  }

  .tier-error {
    background: var(--state-error);
  }

  /* Same yellow as the "Fast fertig"/"Almost finished" tile override
     (see FryerTile.svelte / app.css's --state-near-completion) — reused
     exactly, not a second yellow, so the pill and the tile it's
     summarizing always match. Needs its own dark text colour, same
     reasoning as Heating's dark-on-amber: white text on such a bright
     yellow doesn't have enough contrast. */
  .tier-near-completion {
    background: var(--state-near-completion);
    color: var(--state-near-completion-fg);
  }

  .tier-ready {
    background: var(--opelka-blue);
  }

  .tier-none {
    background: var(--tier-none-bg);
  }

  .logo-panel {
    flex: 0 0 auto;
    background: var(--logo-panel-bg);
    border-radius: var(--radius);
    padding: clamp(0.3rem, 0.6vh, 0.6rem) clamp(0.6rem, 1vw, 1rem);
    display: inline-flex;
  }

  .logo-panel img {
    height: clamp(1.75rem, 4vh, 3.25rem);
    width: auto;
  }
</style>
