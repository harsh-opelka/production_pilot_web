<script>
  import { flip } from 'svelte/animate';
  import FryerTile from './FryerTile.svelte';
  import MachineListRow from './MachineListRow.svelte';
  import { translate } from './translations.js';

  let { group, mode = 'block', language = 'en', productivityByIp = {} } = $props();
</script>

<section class="group">
  <h2 class="group-header">{group.name} <span class="group-type">({group.type})</span></h2>

  {#if mode === 'block'}
    <div class="tiles block">
      {#each group.plcs as plc (plc.ip)}
        <div animate:flip={{ duration: 300 }}>
          <FryerTile {plc} {language} />
        </div>
      {/each}
    </div>
  {:else}
    <div class="table-wrap">
      <table class="machine-table">
        <thead>
          <tr>
            <th>{translate(language, 'stats_col_unit')}</th>
            <th>{translate(language, 'list_col_status')}</th>
            <th>{translate(language, 'list_col_time')}</th>
            <th>{translate(language, 'list_col_recipe')}</th>
            <th>{translate(language, 'list_col_productivity')}</th>
          </tr>
        </thead>
        <tbody>
          {#each group.plcs as plc (plc.ip)}
            <MachineListRow {plc} {language} productivityPct={productivityByIp[plc.ip] ?? null} />
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</section>

<style>
  .group {
    margin-bottom: clamp(1.25rem, 2.5vh, 2.5rem);
  }

  .group-header {
    font-size: var(--font-group-header);
    font-weight: 700;
    margin: 0 0 clamp(0.5rem, 1vh, 1rem);
    color: var(--text-primary);
  }

  .group-type {
    font-weight: 400;
    color: var(--text-secondary);
  }

  .tiles.block {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(clamp(11.25rem, 15vw, 15rem), 1fr));
    gap: clamp(0.75rem, 1.2vw, 1.5rem);
    align-items: start;
  }

  .table-wrap {
    overflow-x: auto;
    background: var(--bg-panel);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
  }

  .machine-table {
    width: 100%;
    border-collapse: collapse;
  }

  .machine-table thead th {
    text-align: left;
    font-size: var(--font-tile-sub);
    font-weight: 600;
    color: var(--text-secondary);
    padding: clamp(0.5rem, 1vh, 0.85rem) clamp(0.75rem, 1.2vw, 1.25rem);
    border-bottom: 1px solid var(--border-color);
    white-space: nowrap;
  }
</style>
