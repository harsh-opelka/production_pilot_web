<script>
  import { machinesState, wsConnected, lang } from './stores.js';
  import { translate } from './translations.js';

  let visible = $derived(!$wsConnected || !$machinesState.connected);
</script>

{#if visible}
  <div class="banner" role="alert">
    {translate($lang, 'connection_lost')}
  </div>
{/if}

<style>
  .banner {
    flex-shrink: 0;
    background: var(--danger-bg);
    color: var(--danger-fg);
    font-size: var(--font-banner);
    font-weight: 700;
    text-align: center;
    padding: clamp(0.5rem, 1.2vh, 1rem);
  }
</style>
