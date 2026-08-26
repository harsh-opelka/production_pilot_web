<script>
  import { onMount } from 'svelte';
  import { theme, page, uiScale, auth } from './lib/stores.js';
  import { fetchInitialState, connectWebSocket } from './lib/websocket.js';
  import Sidebar from './lib/Sidebar.svelte';
  import TopBar from './lib/TopBar.svelte';
  import ConnectionBanner from './lib/ConnectionBanner.svelte';
  import Dashboard from './lib/Dashboard.svelte';
  import Statistics from './lib/Statistics.svelte';
  import ServicePage from './lib/ServicePage.svelte';
  import Footer from './lib/Footer.svelte';

  $effect(() => {
    document.documentElement.dataset.theme = $theme;
  });

  $effect(() => {
    document.documentElement.style.setProperty('--ui-scale', $uiScale);
  });

  // Logged out (fresh visit, explicit logout, or a 401 from any
  // protected call — see serviceApi.js) -> drop back to Production with
  // no sidebar, same as a fresh visit. Covers navigating away from a
  // page the current level can no longer see (e.g. a Service session
  // that expired while the wizard was open).
  $effect(() => {
    if (!$auth.token) page.set('dashboard');
  });

  onMount(async () => {
    await fetchInitialState();
    connectWebSocket();
  });
</script>

<div class="app">
  <div class="body">
    {#if $auth.token}
      <Sidebar />
    {/if}
    <div class="main">
      <TopBar />
      <ConnectionBanner />
      <div class="content">
        {#if $page === 'statistics'}
          <Statistics />
        {:else if $page === 'service'}
          <ServicePage />
        {:else}
          <Dashboard />
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
