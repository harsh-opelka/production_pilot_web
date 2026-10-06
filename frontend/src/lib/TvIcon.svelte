<script>
  // Neutral monitor icon marking where a TV hangs on the floor layout.
  // Inline SVG drawn in currentColor, so it follows the theme's text colour.
  let { title = 'TV' } = $props();
</script>

<svg class="tv-icon" viewBox="0 0 64 48" role="img" aria-label={title}>
  <rect x="3" y="3" width="58" height="34" rx="3" fill="none" stroke="currentColor" stroke-width="3" />
  <rect x="9" y="9" width="46" height="22" rx="1" fill="currentColor" opacity="0.12" />
  <path d="M26 37 L24 44 M38 37 L40 44 M20 45 H44" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" />
</svg>

<style>
  .tv-icon {
    display: block;
    width: 100%;
    height: 100%;
  }
</style>
