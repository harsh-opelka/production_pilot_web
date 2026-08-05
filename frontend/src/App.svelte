<script>
  import { onMount } from 'svelte';
  import { theme, page } from './lib/stores.js';
  import { fetchInitialState, connectWebSocket } from './lib/websocket.js';
  import Sidebar from './lib/Sidebar.svelte';
  import TopBar from './lib/TopBar.svelte';
  import ConnectionBanner from './lib/ConnectionBanner.svelte';
  import Dashboard from './lib/Dashboard.svelte';
  import ServicePage from './lib/ServicePage.svelte';

  $effect(() => {
    document.documentElement.dataset.theme = $theme;
  });

  onMount(async () => {
    await fetchInitialState();
    connectWebSocket();
  });
</script>

<div class="app">
  <Sidebar />
  <div class="main">
    <TopBar />
    <ConnectionBanner />
    <div class="content">
      {#if $page === 'dashboard'}
        <Dashboard />
      {:else}
        <ServicePage />
      {/if}
    </div>
  </div>
</div>

<style>
  .app {
    height: 100%;
    display: flex;
  }

  .main {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    height: 100%;
  }

  .content {
    flex: 1;
    min-height: 0;
  }
</style>
