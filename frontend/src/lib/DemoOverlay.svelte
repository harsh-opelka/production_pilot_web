<script>
  // Demo Mode player: full-screen overlay above the whole app with the
  // recorded demo, looping (autoplay + loop + muted + playsinline — muted
  // is what lets browsers autoplay; there's no audio anyway). Only a seek
  // bar with mm:ss at the bottom and an X at the top right; both auto-hide
  // after a few seconds without mouse/touch movement. Click/tap the video
  // to pause/resume, X or Esc to go back to the live screen.
  //
  // Just a video player: the live dashboard stays mounted underneath and
  // keeps receiving state, so it is current the moment X is pressed.
  // Errors: an error after playback had started (network blip) is retried
  // once in place; stalled/waiting are left to the browser (not errors).
  // If the newest version can't load, the previous good version is played
  // instead; only if that fails too does it fall back to the live screen.
  // The real cause (HTTP status, video error code/message) goes to the
  // console and, at Service level, into a small detail line.
  import { onDestroy } from 'svelte';
  import { lang, auth } from './stores.js';
  import { translate } from './translations.js';
  import {
    displayMode,
    demoStatus,
    demoMessage,
    demoButtonVisible,
    demoVideoUrl,
    formatClock,
    showDemoMessage,
    nextPlaybackSource,
  } from './demoMode.js';

  const HIDE_CONTROLS_MS = 3000;

  let video = $state();
  let current = $state(0);
  let duration = $state(NaN);
  let controlsVisible = $state(true);
  let seeking = $state(false);
  let hideTimer;
  let which = $state('current'); // 'current' | 'previous' (fallback)
  let serviceDetail = $state('');
  let metadataLoaded = false;
  let reloadTried = false;
  let resumeAt = null;

  let src = $derived(demoVideoUrl($demoStatus, $auth.token, which));
  let isService = $derived($auth.level === 'service');

  // Every time Demo Mode opens: start from the newest version again.
  let lastMode = null;
  $effect(() => {
    const mode = $displayMode;
    if (mode === 'demo' && lastMode !== 'demo') {
      which = 'current';
      serviceDetail = '';
      metadataLoaded = false;
      reloadTried = false;
    }
    lastMode = mode;
  });
  let seekable = $derived(Number.isFinite(duration) && duration > 0);
  // Messages normally show under the Demo button; when this screen can't
  // see the button (e.g. a reload fell back to Live), show them here.
  let toast = $derived(
    $displayMode === 'live' && $demoMessage && !demoButtonVisible($auth.level, $demoStatus.show_for_all) ? $demoMessage : null,
  );

  // A reload / kiosk restart that comes back in Demo Mode while the demo is
  // gone falls back to the live screen instead of showing a black screen.
  $effect(() => {
    if ($displayMode === 'demo' && $demoStatus.loaded && !$demoStatus.exists) {
      displayMode.set('live');
      showDemoMessage('demo_load_failed');
    }
  });

  function close() {
    displayMode.set('live');
  }

  function poke() {
    controlsVisible = true;
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => {
      if (!seeking) controlsVisible = false;
    }, HIDE_CONTROLS_MS);
  }

  $effect(() => {
    if ($displayMode === 'demo') poke();
  });
  onDestroy(() => clearTimeout(hideTimer));

  function togglePlay() {
    if (!video) return;
    if (video.paused) video.play().catch(() => {});
    else video.pause();
    poke();
  }

  // What the server says for this URL (the video element only reports a
  // generic "format error" for e.g. a 401 or 404).
  async function probe(url) {
    try {
      const res = await fetch(url, { headers: { Range: 'bytes=0-0' }, cache: 'no-store' });
      return `HTTP ${res.status}`;
    } catch {
      return 'no response from the server';
    }
  }

  async function onError() {
    const code = video?.error?.code;
    const message = video?.error?.message ?? '';
    if (metadataLoaded && !reloadTried && video) {
      // Was playing fine: treat as recoverable once, reload in place.
      reloadTried = true;
      resumeAt = video.currentTime;
      metadataLoaded = false;
      video.load();
      video.play().catch(() => {});
      return;
    }
    const failedSrc = src;
    const failedWhich = which;
    const http = await probe(failedSrc);
    const detail = `${failedWhich}: ${http}, video error ${code ?? '?'}${message ? ` (${message})` : ''}`;
    console.error('[demo] playback failed', {
      which: failedWhich,
      url: failedSrc.replace(/token=[^&]+/, 'token=…'),
      http,
      videoErrorCode: code,
      videoErrorMessage: message,
    });
    const next = nextPlaybackSource(failedWhich, $demoStatus);
    if (next && $displayMode === 'demo') {
      which = next;
      metadataLoaded = false;
      reloadTried = false;
      serviceDetail = translate($lang, 'demo_playing_previous', { detail });
      return;
    }
    displayMode.set('live');
    if (isService) showDemoMessage('demo_load_failed_detail', { detail }, 20000);
    else showDemoMessage('demo_load_failed');
  }

  function onLoadedMetadata() {
    duration = video.duration;
    metadataLoaded = true;
    if (resumeAt != null) {
      video.currentTime = resumeAt;
      resumeAt = null;
    }
  }

  function onSeekInput(event) {
    seeking = true;
    const t = Number(event.currentTarget.value);
    current = t;
    if (video) video.currentTime = t;
    poke();
  }

  function onKeydown(event) {
    if ($displayMode === 'demo' && event.key === 'Escape') close();
  }
</script>

<svelte:window onkeydown={onKeydown} />

{#if toast}
  <p class="toast" role="status">{translate($lang, toast.key, toast.vars)}</p>
{/if}

{#if $displayMode === 'demo' && $demoStatus.exists}
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="overlay" class:idle={!controlsVisible} onpointermove={poke} onpointerdown={poke}>
    <!-- svelte-ignore a11y_media_has_caption -->
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <video
      bind:this={video}
      {src}
      autoplay
      loop
      muted
      playsinline
      disablepictureinpicture
      preload="auto"
      onclick={togglePlay}
      onerror={onError}
      ontimeupdate={() => !seeking && (current = video.currentTime)}
      ondurationchange={() => (duration = video.duration)}
      onloadedmetadata={onLoadedMetadata}
    ></video>

    {#if isService && serviceDetail}
      <p class="service-detail" class:hidden={!controlsVisible}>{serviceDetail}</p>
    {/if}

    <button type="button" class="close" class:hidden={!controlsVisible} aria-label={translate($lang, 'demo_close')} onclick={close}>
      ✕
    </button>

    <div class="controls" class:hidden={!controlsVisible}>
      <span class="time">{formatClock(current)}</span>
      <input
        type="range"
        min="0"
        max={seekable ? duration : 1}
        step="0.1"
        value={seekable ? current : 0}
        disabled={!seekable}
        aria-label={translate($lang, 'demo_seek')}
        oninput={onSeekInput}
        onchange={() => (seeking = false)}
        onpointerup={() => (seeking = false)}
      />
      <span class="time">{seekable ? formatClock(duration) : '--:--'}</span>
    </div>
  </div>
{/if}

<style>
  .toast {
    position: fixed;
    left: 50%;
    bottom: 2.5rem;
    z-index: 1500;
    transform: translateX(-50%);
    max-width: min(32rem, 90vw);
    margin: 0;
    padding: 0.6rem 1rem;
    font-size: var(--font-tile-sub);
    color: var(--text-primary);
    background: var(--bg-panel);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.3);
  }

  /* Above everything, including the header, legend and dialogs. */
  .overlay {
    position: fixed;
    inset: 0;
    z-index: 3000;
    background: var(--bg-app);
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .overlay.idle {
    cursor: none;
  }

  /* contain = whole picture, letterboxed in the page colour, never cropped. */
  video {
    width: 100%;
    height: 100%;
    object-fit: contain;
    background: var(--bg-app);
  }

  .close {
    position: absolute;
    top: clamp(0.75rem, 2vh, 1.5rem);
    right: clamp(0.75rem, 2vw, 1.5rem);
    width: clamp(2.75rem, 4vw, 3.75rem);
    height: clamp(2.75rem, 4vw, 3.75rem);
    font-size: clamp(1.3rem, 2vw, 1.8rem);
    line-height: 1;
    color: #ffffff;
    background: rgba(15, 23, 42, 0.7);
    border: 1px solid rgba(255, 255, 255, 0.35);
    border-radius: 50%;
    cursor: pointer;
    transition: opacity 0.3s;
  }

  .service-detail {
    position: absolute;
    top: clamp(0.75rem, 2vh, 1.5rem);
    left: clamp(0.75rem, 2vw, 1.5rem);
    max-width: min(40rem, 70vw);
    margin: 0;
    padding: 0.4rem 0.7rem;
    font-size: 0.85rem;
    color: #ffffff;
    background: rgba(15, 23, 42, 0.75);
    border-radius: var(--radius);
    transition: opacity 0.3s;
  }

  .controls {
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0;
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: clamp(0.75rem, 2vh, 1.5rem) clamp(1rem, 3vw, 2.5rem);
    background: linear-gradient(to top, rgba(15, 23, 42, 0.85), rgba(15, 23, 42, 0));
    color: #ffffff;
    transition: opacity 0.3s;
  }

  .hidden {
    opacity: 0;
    pointer-events: none;
  }

  .time {
    font-variant-numeric: tabular-nums;
    font-weight: 600;
    font-size: clamp(0.9rem, 1.1vw, 1.2rem);
    min-width: 3.5em;
    text-align: center;
  }

  /* Generous hit area (2.75rem tall) for a finger or a mouse. */
  input[type='range'] {
    flex: 1;
    height: 2.75rem;
    margin: 0;
    background: transparent;
    accent-color: var(--next-accent);
    cursor: pointer;
    -webkit-appearance: none;
    appearance: none;
  }

  input[type='range']:disabled {
    opacity: 0.4;
    cursor: default;
  }

  input[type='range']::-webkit-slider-runnable-track {
    height: 0.5rem;
    border-radius: 0.25rem;
    background: rgba(255, 255, 255, 0.35);
  }

  input[type='range']::-webkit-slider-thumb {
    -webkit-appearance: none;
    width: 1.4rem;
    height: 1.4rem;
    margin-top: -0.45rem;
    border-radius: 50%;
    background: #ffffff;
    border: 3px solid var(--next-accent);
  }

  input[type='range']::-moz-range-track {
    height: 0.5rem;
    border-radius: 0.25rem;
    background: rgba(255, 255, 255, 0.35);
  }

  input[type='range']::-moz-range-thumb {
    width: 1.1rem;
    height: 1.1rem;
    border-radius: 50%;
    background: #ffffff;
    border: 3px solid var(--next-accent);
  }
</style>
