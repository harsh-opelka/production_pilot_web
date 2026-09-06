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
  .view-toggle {
    font-size: var(--font-view-toggle);
    font-weight: 600;
    padding: clamp(0.4rem, 0.7vh, 0.7rem) clamp(0.9rem, 1.4vw, 1.5rem);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    background: var(--opelka-blue);
    color: var(--opelka-blue-fg);
  }
</style>
