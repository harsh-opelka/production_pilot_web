<script>
  import { lang } from './stores.js';
  import { translate } from './translations.js';
  import ChangePasswordCard from './ChangePasswordCard.svelte';
  import ChangeManagementPasswordCard from './ChangeManagementPasswordCard.svelte';
  import RecordingCard from './RecordingCard.svelte';
  import DataSourceCard from './DataSourceCard.svelte';
  import InstallWizard from './InstallWizard.svelte';

  let wizardOpen = $state(false);
</script>

<div class="service-home">
  <h1>{translate($lang, 'service_heading')}</h1>

  <section class="section">
    <h2 class="section-heading">{translate($lang, 'service_section_setup')}</h2>
    <div class="cards">
      <button class="card wizard-card" onclick={() => (wizardOpen = true)}>
        <h3>{translate($lang, 'service_wizard_title')}</h3>
        <p>{translate($lang, 'service_wizard_desc')}</p>
      </button>

      <div class="card">
        <DataSourceCard />
      </div>
    </div>
  </section>

  <section class="section">
    <h2 class="section-heading">{translate($lang, 'service_section_security')}</h2>
    <div class="cards">
      <div class="card">
        <ChangePasswordCard />
      </div>

      <div class="card">
        <ChangeManagementPasswordCard />
      </div>
    </div>
  </section>

  <section class="section">
    <h2 class="section-heading">{translate($lang, 'service_section_data')}</h2>
    <div class="cards">
      <div class="card">
        <RecordingCard />
      </div>
    </div>
  </section>
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
    overflow-wrap: break-word;
  }

  .section {
    margin-bottom: clamp(1.5rem, 3vh, 2.5rem);
  }

  .section:last-child {
    margin-bottom: 0;
  }

  /* Small-caps-style muted uppercase label separating the three groups —
     deliberately much smaller than the card titles below it, purely a
     visual divider, not a heading competing for attention. */
  .section-heading {
    margin: 0 0 clamp(0.6rem, 1.2vh, 1rem);
    font-size: calc(var(--font-toggle) * 0.8);
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-secondary);
  }

  .cards {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 320px), 1fr));
    gap: clamp(1rem, 2vw, 2rem);
    /* Grid's default — explicit here because a stray override elsewhere
       is exactly what would reintroduce mismatched card heights within a
       row (e.g. Installation Wizard next to Data Source once its Demo
       Controls panel is expanded and much taller). */
    align-items: stretch;
  }

  .card {
    background: var(--bg-panel);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    padding: clamp(1.25rem, 2.2vw, 2rem);
    /* Grid items default to min-width:auto, which lets long unbreakable
       content (long German labels/words) force the column wider than the
       track instead of wrapping inside the card — this is what actually
       caused the reported overflow, not the grid/card sizing itself. */
    min-width: 0;
    overflow-wrap: break-word;
  }

  .wizard-card {
    text-align: left;
    font-family: inherit;
    color: inherit;
    border-color: var(--border-color);
    transition: border-color 0.15s;
    /* Buttons default to white-space:pre in Chromium/Firefox (same fix
       as Sidebar.svelte's nav buttons) — without this, a long German
       title/description inside the button never wraps and overflows the
       card instead of shrinking to fit it. */
    white-space: normal;
  }

  .wizard-card:hover {
    border-color: var(--accent);
  }

  .wizard-card h3 {
    margin: 0 0 0.5rem;
    font-size: var(--font-group-header);
    color: var(--text-primary);
    overflow-wrap: break-word;
  }

  .wizard-card p {
    margin: 0;
    color: var(--text-secondary);
    font-size: var(--font-toggle);
    overflow-wrap: break-word;
  }
</style>
