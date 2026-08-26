<script>
  import { onMount } from 'svelte';
  import { theme, page, uiScale } from './lib/stores.js';
  import { fetchInitialState, connectWebSocket } from './lib/websocket.js';
  import Sidebar from './lib/Sidebar.svelte';
  import TopBar from './lib/TopBar.svelte';
  import ConnectionBanner from './lib/ConnectionBanner.svelte';
  import Dashboard from './lib/Dashboard.svelte';
  import ServicePage from './lib/ServicePage.svelte';
  import Footer from './lib/Footer.svelte';

  $effect(() => {
    document.documentElement.dataset.theme = $theme;
  });

  $effect(() => {
    document.documentElement.style.setProperty('--ui-scale', $uiScale);
  });

  onMount(async () => {
    await fetchInitialState();
    connectWebSocket();
  });
</script>

<div class="app">
  <div class="body">
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
  <Footer />
</div>

<style>
  /* Column: the sidebar+main row fills whatever height remains above the
     footer (flex:1 + min-height:0), and Footer is a normal flex item
     below it — never position:fixed — so it always keeps its own space
     and can't be covered by or clipped behind scaled dashboard content. */
  .app {
    height: 100%;
    display: flex;
    flex-direction: column;
  }

  .body {
    flex: 1;
    min-height: 0;
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
