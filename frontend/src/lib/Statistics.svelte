<script>
  import { lang } from './stores.js';
  import { translate } from './translations.js';
</script>

<div class="statistics">
  <p>{translate($lang, 'coming_soon')}</p>
</div>

<style>
  .statistics {
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-secondary);
    font-size: var(--font-group-header);
  }
</style>
