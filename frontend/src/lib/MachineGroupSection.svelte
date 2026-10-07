<script>
  import FryerTile from './FryerTile.svelte';
  import MachineListRow from './MachineListRow.svelte';
  import { translate } from './translations.js';

  // floor: rendered as one block on the floor layout (Dashboard.svelte) —
  // a fixed single row (orientation 'horizontal') or column ('vertical')
  // of natural-size tiles, instead of the auto-filling grid.
  let {
    group,
    mode = 'block',
    language = 'en',
    productivityByIp = {},
    nextActionIp = null,
    floor = false,
    orientation = 'horizontal',
  } = $props();

  // Tiles never move with live state: fixed order by machine number,
  // keyed by IP so Svelte never re-mounts or re-orders them. Only the
  // NEXT badge (and the banner) move.
  let plcs = $derived([...group.plcs].sort((a, b) => a.unit_number - b.unit_number));
</script>

<section class="group" class:floor>
  <h2 class="group-header">{group.name}</h2>

  {#if mode === 'block'}
    <div
      class="tiles block"
      class:floor-row={floor && orientation !== 'vertical'}
      class:floor-column={floor && orientation === 'vertical'}
      style={floor ? `--tile-count: ${plcs.length};` : ''}
    >
      {#each plcs as plc (plc.ip)}
        <FryerTile {plc} {language} isNext={plc.ip === nextActionIp} />
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
            <th>{translate(language, 'list_col_temperature')}</th>
            <th>{translate(language, 'list_col_productivity')}</th>
          </tr>
        </thead>
        <tbody>
          {#each plcs as plc (plc.ip)}
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
    /* Explicit (not 'normal') so the floor layout editor can compute a
       group's height exactly — see floorLayout.naturalGroupSize. */
    line-height: 1.2;
    /* Bumped up from clamp(0.5rem, 1vh, 1rem) for noticeably more
       breathing room between the group name and its row of tiles. */
    margin: 0 0 clamp(1.25rem, 2.75vh, 2.25rem);
    color: var(--text-primary);
  }

  /* padding-top: room for the NEXT badge, which sticks 0.6rem out above
     its tile, so it never touches the group title. */
  .tiles.block {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(clamp(11.25rem, 15vw, 15rem), 1fr));
    gap: clamp(0.75rem, 1.2vw, 1.5rem);
    align-items: start;
    padding-top: 0.6rem;
  }

  /* Floor-layout block (Dashboard.svelte): same natural sizes as the
     stacked view — only the tile count per row/column is fixed.
     --floor-tile-w is the stacked grid's actual (stretched) column width,
     set by Dashboard.svelte (floorLayout.stackedTileWidth). */
  .group.floor {
    margin: 0;
    width: max-content;
  }

  .group.floor .group-header {
    white-space: nowrap;
  }

  .tiles.block.floor-row {
    grid-template-columns: repeat(var(--tile-count), var(--floor-tile-w, clamp(11.25rem, 15vw, 15rem)));
  }

  .tiles.block.floor-column {
    grid-template-columns: var(--floor-tile-w, clamp(11.25rem, 15vw, 15rem));
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
