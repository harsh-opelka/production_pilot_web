<script>
  import { lang } from './stores.js';
  import { translate } from './translations.js';
  import { login, ServiceApiError } from './serviceApi.js';

  let open = $state(false);
  let password = $state('');
  let error = $state('');
  let loading = $state(false);
  let passwordInput;

  // Exposed for TopBar.svelte to call via bind:this — the login trigger
  // is now the clickable Opelka logo instead of a standalone hamburger
  // button, but the modal itself (and everything below) is unchanged.
  export function openGate() {
    open = true;
    error = '';
    password = '';
  }

  function closeGate() {
    open = false;
    error = '';
    password = '';
  }

  async function submit(event) {
    event.preventDefault();
    if (loading || !password) return;
    error = '';
    loading = true;
    try {
      await login(password);
      // Success — $auth.token becomes truthy, App.svelte renders the
      // sidebar and TopBar.svelte's logo click handler stops firing
      // openGate (see its own {#if !$auth.token} guard).
      password = '';
      open = false;
    } catch (err) {
      error =
        err instanceof ServiceApiError && err.status === 429
          ? translate($lang, 'service_too_many_attempts')
          : translate($lang, 'auth_gate_incorrect');
    } finally {
      loading = false;
    }
  }

  $effect(() => {
    if (open) passwordInput?.focus();
  });
</script>

{#if open}
  <div class="overlay" onclick={closeGate} role="presentation">
    <form class="card" onsubmit={submit} onclick={(e) => e.stopPropagation()}>
      <button type="button" class="close" onclick={closeGate} aria-label={translate($lang, 'close')}>×</button>
      <h2>{translate($lang, 'auth_gate_title')}</h2>

      <label class="field">
        <span>{translate($lang, 'auth_gate_prompt')}</span>
        <input type="password" bind:value={password} bind:this={passwordInput} />
      </label>

      {#if error}
        <p class="error">{error}</p>
      {/if}

      <button type="submit" disabled={loading || !password}>{translate($lang, 'unlock')}</button>
    </form>
  </div>
{/if}

<style>
  /* The overlay itself is position:fixed, so wherever TopBar.svelte
     mounts this component (see bind:this there) doesn't affect it — it
     still covers the full viewport regardless of where in the DOM it's
     mounted. */
  .overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 100;
  }

  .card {
    /* Lets h2 below size itself off the card's own (padding-excluded)
       content width via cqw — see h2 — rather than the viewport's, so
       the heading keeps fitting on one line regardless of --ui-scale
       inflating the card's padding/or the card itself being capped at
       420px well before the viewport is. */
    container-type: inline-size;
    position: relative;
    background: var(--bg-panel);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    /* Floor is a fixed px, not rem, for the same reason as h2's floor
       below: this card's width is capped independently of --ui-scale, so
       a rem-based floor here would keep eating more and more of that
       fixed width as scale increases — on a narrow viewport at a high
       scale that can consume the entire card, leaving h2 no room to
       shrink into no matter how small its own font gets. */
    padding: clamp(12px, 3vh, 2.5rem);
    width: min(90vw, 420px);
    display: flex;
    flex-direction: column;
    gap: clamp(0.75rem, 1.5vh, 1.25rem);
  }

  .close {
    position: absolute;
    top: 0.5rem;
    right: 0.5rem;
    background: transparent;
    border: none;
    font-size: 1.5rem;
    line-height: 1;
    color: var(--text-secondary);
    padding: 0.25rem;
  }

  /* --font-group-header scales with --ui-scale (rem-based), but this
     card's width is capped at a fixed 420px regardless of --ui-scale —
     so that font alone can outgrow the card at high scale and wrap
     "Access Required"/"Zugang erforderlich" onto two lines. Sized off
     the card's own content-box width (cqw, via .card's container-type
     above) instead: shrinks to fit whatever room is actually left
     after padding, on any viewport, at any --ui-scale. The plain
     rem value first is a fallback for browsers without container query
     units (ignored — not overridden — wherever cqw is supported).

     The floor is a fixed px, not rem: rem still scales with --ui-scale,
     and at a high scale combined with a narrow viewport the card's
     (rem-based) padding can eat so much of its own fixed-px width that
     even a modest rem floor no longer fits — which would fall through
     to the ellipsis safety net below instead of actually shrinking. A
     bare px floor has no such ceiling, so cqw can keep shrinking the
     text all the way down to something still legible. */
  h2 {
    /* Flex items default to min-width: auto, i.e. never shrink below
       their own content's intrinsic size — with white-space: nowrap
       that intrinsic size is the FULL text at the current font-size, so
       without this override h2 would just push past the card's edge
       instead of ever actually engaging overflow/ellipsis (or, further
       up, actually being constrained enough for cqw to shrink it). */
    min-width: 0;
    margin: 0;
    /* Reserves room for .close (absolutely positioned, so it doesn't
       otherwise take up any flow space h2 would know to avoid) — its
       own right offset + width + a little clearance. */
    padding-right: 2.25rem;
    font-size: 1.5rem;
    /* 7.5cqw (not a rounder 9-10cqw) leaves enough margin that the
       longer German heading ("Zugang erforderlich", ~20 chars vs.
       "Access Required"'s ~15) still fits at the size this picks —
       cqw alone has no way to account for per-string character count,
       so this is deliberately conservative for both languages rather
       than tuned to just the shorter English string. */
    font-size: clamp(11px, 6cqw, 1.6rem);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--text-primary);
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
    font-size: var(--font-toggle);
    color: var(--text-secondary);
  }

  input {
    font-size: var(--font-toggle);
    padding: clamp(0.5rem, 1vh, 0.75rem);
    border-radius: var(--radius);
    border: 1px solid var(--border-color);
    background: var(--bg-app);
    color: var(--text-primary);
  }

  .error {
    margin: 0;
    color: var(--danger-bg);
    font-size: var(--font-toggle);
    font-weight: 600;
  }

  button[type='submit'] {
    font-size: var(--font-toggle);
    font-weight: 600;
    padding: clamp(0.6rem, 1.1vh, 0.9rem);
    border: none;
    border-radius: var(--radius);
    background: var(--accent);
    color: var(--opelka-blue-fg);
  }

  button[type='submit']:disabled {
    opacity: 0.5;
    cursor: default;
  }
</style>
