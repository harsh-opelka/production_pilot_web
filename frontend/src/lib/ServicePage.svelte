<script>
  import { serviceToken } from './stores.js';
  import LoginPrompt from './LoginPrompt.svelte';
  import ServiceHome from './ServiceHome.svelte';
</script>

{#if $serviceToken}
  <ServiceHome />
{:else}
  <LoginPrompt />
{/if}
