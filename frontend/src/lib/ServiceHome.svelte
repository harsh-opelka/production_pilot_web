<script>
  import { lang } from './stores.js';
  import { translate } from './translations.js';
  import ChangePasswordCard from './ChangePasswordCard.svelte';
  import InstallWizard from './InstallWizard.svelte';

  let wizardOpen = $state(false);
</script>

<div class="service-home">
  <h1>{translate($lang, 'service_heading')}</h1>

  <div class="cards">
    <button class="card wizard-card" onclick={() => (wizardOpen = true)}>
      <h2>{translate($lang, 'service_wizard_title')}</h2>
      <p>{translate($lang, 'service_wizard_desc')}</p>
    </button>

    <div class="card">
      <ChangePasswordCard />
    </div>
  </div>
</div>

{#if wizardOpen}
  <InstallWizard onClose={() => (wizardOpen = false)} />
{/if}

<style>
  .service-home {
    height: 100%;
    overflow-y: auto;
    padding: clamp(1rem, 2vh, 2rem) clamp(1rem, 2vw, 2rem);
  }

  h1 {
    margin: 0 0 clamp(1rem, 2vh, 1.75rem);
    font-size: var(--font-group-header);
    color: var(--text-primary);
  }

  .cards {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 320px), 1fr));
    gap: clamp(1rem, 2vw, 2rem);
    align-items: start;
  }

  .card {
    background: var(--bg-panel);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    padding: clamp(1.25rem, 2.2vw, 2rem);
  }

  .wizard-card {
    text-align: left;
    font-family: inherit;
    color: inherit;
    border-color: var(--border-color);
    transition: border-color 0.15s;
  }

  .wizard-card:hover {
    border-color: var(--accent);
  }

  .wizard-card h2 {
    margin: 0 0 0.5rem;
    font-size: var(--font-group-header);
    color: var(--text-primary);
  }

  .wizard-card p {
    margin: 0;
    color: var(--text-secondary);
    font-size: var(--font-toggle);
  }
</style>
