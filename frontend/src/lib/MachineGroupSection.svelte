<script>
  import { flip } from 'svelte/animate';
  import FryerTile from './FryerTile.svelte';

  let { group, mode = 'block', language = 'en' } = $props();
</script>

<section class="group">
  <h2 class="group-header">{group.name} <span class="group-type">({group.type})</span></h2>

  <div class="tiles {mode}">
    {#each group.plcs as plc (plc.ip)}
      <div animate:flip={{ duration: 300 }}>
        <FryerTile {plc} {mode} {language} />
      </div>
    {/each}
  </div>
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

  .tiles.list {
    display: flex;
    flex-direction: column;
    gap: clamp(0.5rem, 0.8vh, 0.85rem);
  }
</style>
