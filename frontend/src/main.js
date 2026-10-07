import { mount } from 'svelte'
import './app.css'
import App from './App.svelte'
import { loadStateColors } from './lib/stateColors.js'

// State colours come from the backend (Service-configurable, no frontend
// copy) — wait for them briefly so the first paint already has them, but
// never block the app on an unreachable server: websocket.js retries.
const COLORS_WAIT_MS = 3000
Promise.race([loadStateColors(), new Promise((resolve) => setTimeout(resolve, COLORS_WAIT_MS))]).then(() => {
  mount(App, { target: document.getElementById('app') })
})
