<script>
  import logo from '../assets/opelka_logo.png';
  import { machinesState, lang, page, auth, sidebarOpen } from './stores.js';
  import { translate } from './translations.js';
  import { describeNextAction } from './nextAction.js';
  import AuthGate from './AuthGate.svelte';
  import KpiSummary from './KpiSummary.svelte';

  let nextAction = $derived(describeNextAction($machinesState.next_action, $lang));

  // bind:this target for AuthGate below — the login trigger used to be a
  // standalone hamburger button (see AuthGate.svelte's history); now it's
  // the Opelka logo itself, so TopBar calls straight into AuthGate's
  // exported openGate() instead of AuthGate rendering its own button.
  let authGate;

  // Not authenticated yet -> the logo starts the login flow (unchanged).
  // Already authenticated -> the logo purely toggles sidebar visibility
  // (see stores.js's sidebarOpen) and never re-prompts for the password —
  // closing/reopening the sidebar must not look like logging out. See
  // serviceApi.js's login()/logout() for where sidebarOpen itself gets
  // set true/false.
  function handleLogoClick() {
    if ($auth.token) {
      sidebarOpen.update((open) => !open);
    } else {
      authGate.openGate();
    }
  }
</script>

<header class="topbar">
  <div class="next-action">
    <div class="next-action-box">
      <span class="na-label">{translate($lang, 'next_action_prefix')}</span>
      {#if nextAction.nothingToDo}
        <!-- Nothing to do right now: a smiley instead of the dash, centred.
             Inline SVG rather than an emoji — the Jetson may have no emoji
             font. 1em square, so it matches the banner text size. -->
        <span class="na-content na-smiley">
          <svg
            class="smiley"
            viewBox="0 0 24 24"
            role="img"
            aria-label={translate($lang, 'next_action_nothing_to_do')}
          >
            <circle cx="12" cy="12" r="11" fill="#facc15" stroke="#a16207" stroke-width="1" />
            <circle cx="8.5" cy="9.5" r="1.5" fill="#1c1c1c" />
            <circle cx="15.5" cy="9.5" r="1.5" fill="#1c1c1c" />
            <path d="M7.3 14 Q12 18.8 16.7 14" fill="none" stroke="#1c1c1c" stroke-width="1.9" stroke-linecap="round" />
          </svg>
        </span>
      {:else if nextAction.unit != null}
        <span class="na-content" title={nextAction.text}>
          <span class="na-unit">{nextAction.unit}</span>
          <span class="na-action">{nextAction.action}</span>
        </span>
      {:else}
        <span class="na-content">{nextAction.text}</span>
      {/if}
    </div>
  </div>

  <div class="right-group">
    {#if $page === 'dashboard'}
      <KpiSummary />
    {/if}

    <!-- Always clickable now — see handleLogoClick above for the two
         behaviors (start login vs. toggle the sidebar) depending on
         whether a session is already authenticated. -->
    <button
      type="button"
      class="logo-panel logo-button"
      onclick={handleLogoClick}
      aria-label={translate($lang, 'menu_tooltip')}
      title={translate($lang, 'menu_tooltip')}
    >
      <img src={logo} alt="Opelka" />
    </button>
  </div>

  <AuthGate bind:this={authGate} />
</header>

<style>
  .topbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    /* Exactly two top-level flex children (.next-action, .right-group) —
       with only two items, space-between puts the ENTIRE leftover gap in
       the one place it belongs: between them. The login-gate button used
       to sit alongside .next-action in a shared .left-group wrapper,
       which is why .next-action itself couldn't just be flex:1 1 auto
       directly — that grouping is gone now that AuthGate lives in
       .right-group instead (see the template above), so .next-action is
       free to sit here on its own and align fully left. */
    justify-content: space-between;
    background: var(--bg-topbar);
    border-bottom: 1px solid var(--border-color);
    padding: clamp(0.5rem, 1.2vh, 1rem) clamp(1rem, 2vw, 2rem);
    /* Row-gap (wrap fallback) and column-gap both bumped up from the
       previous clamp(0.5rem, 1vh, 1rem)/clamp(0.75rem, 1.5vw, 1.5rem) —
       gap is a floor space-between adds on top of, not a ceiling, so
       raising it keeps .next-action/.right-group from ever crowding
       together even when there's little leftover space to distribute. */
    gap: clamp(0.75rem, 2vh, 1.5rem) clamp(1.25rem, 2.5vw, 2.5rem);
    flex-shrink: 0;
  }

  /* flex-grow: 1 so this claims the leftover width up to .right-group,
     widening the block itself rather than leaving blank space next to a
     fixed-size neighbor (there is none now — see .topbar's comment).
     flex-basis 20rem is just a sane starting point before growth; the
     generous max-width still caps it well short of .right-group so the
     two never collide, and flex-shrink: 1 + na-content's overflow-wrap
     still let it wrap onto its own full-width row (via .topbar's
     flex-wrap) rather than being squeezed to a sliver at high --ui-scale. */
  .next-action {
    flex: 1 1 20rem;
    min-width: 0;
    max-width: clamp(24rem, 46vw, 46rem);
    display: flex;
  }

  /* KPI table + logo (+ the login-gate button, pre-login) as one flex
     item: at low viewport width / high --ui-scale, when this doesn't fit
     next to .next-action, the whole group wraps to its own row together
     (via .topbar's flex-wrap) instead of the KPI table wrapping alone and
     ending up squeezed under Next Action while the logo stays put — see
     task spec: "KPI table should sit clearly to the right side of the
     bar". The explicit gap here is a floor for spacing between these
     items that doesn't depend on how much leftover width .topbar's
     space-between has to distribute. */
  .right-group {
    flex: 0 1 auto;
    min-width: 0;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: flex-end;
    gap: clamp(1.25rem, 3vw, 3rem);
  }

  /* One constant card for every action (Tim): only the text changes,
     never the colour. Small label on top (na-label), then the machine
     number in a navy badge (na-unit) and the action text (na-action).
     Border, navy accent bar and shadow are all box-shadows (the two
     inset), so the card keeps exactly its previous size and padding.
     Colours: --next-* tokens in app.css, per theme. */
  .next-action-box {
    flex: 1 1 auto;
    min-width: 0;
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: clamp(0.3rem, 0.6vh, 0.6rem);
    padding: clamp(1rem, 2.4vh, 1.9rem) clamp(1.5rem, 3vw, 2.75rem);
    border-radius: var(--radius);
    background: var(--next-card-bg);
    color: var(--next-text);
    box-shadow:
      inset 5px 0 0 var(--next-accent),
      inset 0 0 0 1px var(--next-card-border),
      var(--next-card-shadow);
  }

  .na-label {
    font-size: calc(var(--font-next-action) * 0.36);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--next-label);
  }

  /* One line: nowrap, at 90 % of the old size so the longest texts
     ("Auf Auto stellen", "Störung prüfen") fit next to the badge; the
     ellipsis is only a last resort at extreme Display Size settings. */
  .na-content {
    display: flex;
    align-items: center;
    gap: 0.4em;
    min-width: 0;
    font-size: calc(var(--font-next-action) * 0.9);
    font-weight: 700;
    line-height: 1.15;
    white-space: nowrap;
  }

  .na-unit {
    flex: 0 0 auto;
    min-width: 1.35em;
    padding: 0.08em 0.3em;
    border-radius: 0.22em;
    background: var(--next-accent);
    color: var(--next-accent-fg);
    text-align: center;
    font-variant-numeric: tabular-nums;
  }

  .na-action {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .na-smiley {
    justify-content: center;
  }

  .smiley {
    display: block;
    width: 1.15em;
    height: 1.15em;
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

  /* Pre-login only (see the {#if !$auth.token} above) — the logo itself
     is the only click target now, so this is a plain <button> reset down
     to .logo-panel's own look (no border/background chrome of its own)
     plus a minimal, deliberately subtle hover/focus affordance: a soft
     ring (reads as a faint tint against the white logo panel, not a
     gradient/glow) and a slight scale. Nothing shows at rest — it should
     still read primarily as a logo, not a button. */
  .logo-button {
    border: none;
    font: inherit;
    cursor: pointer;
    transition: box-shadow 0.15s ease, transform 0.15s ease;
  }

  .logo-button:hover {
    box-shadow: 0 0 0 3px rgba(5, 52, 108, 0.12);
    transform: scale(1.03);
  }

  .logo-button:focus-visible {
    outline: 2px solid var(--opelka-blue);
    outline-offset: 2px;
  }
</style>
