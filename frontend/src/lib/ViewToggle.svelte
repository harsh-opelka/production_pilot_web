<script>
  // Single-button Block/List switch: always shows the name of the view
  // you are NOT currently in. Reused on the Dashboard toolbar and in
  // Settings (Service level) — both read/write the same `view` store, so
  // toggling from either place stays in sync with the other.
  import { view, lang } from './stores.js';
  import { translate } from './translations.js';

  let nextViewLabel = $derived(translate($lang, $view === 'block' ? 'list_view' : 'block_view'));

  function toggle() {
    view.set($view === 'block' ? 'list' : 'block');
  }
</script>

<button type="button" class="view-toggle" onclick={toggle}>
  {nextViewLabel}
</button>

<style>
  /* A secondary control — deliberately smaller than --font-view-toggle
     (which the Statistics screen's snapshot/trend/live tabs still use)
     so it doesn't visually compete with the Next Action block or the
     tiles below it. */
  .view-toggle {
    font-size: clamp(0.75rem, 0.85vw, 0.95rem);
    font-weight: 600;
    padding: clamp(0.25rem, 0.4vh, 0.4rem) clamp(0.55rem, 0.9vw, 0.9rem);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    background: var(--opelka-blue);
    color: var(--opelka-blue-fg);
  }
</style>
