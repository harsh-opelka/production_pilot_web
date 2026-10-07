# Produktionspilot V2

FastAPI backend (`server.py`, `production_pilot/`) and Svelte dashboard (`frontend/`).

```
cd frontend && npm run build     # builds into ../static
cd .. && python server.py        # http://localhost:8000
```

## Demo Mode on the Jetson kiosk

Customer Demo Mode records the Pilot's own browser tab (Demo button on the
Dashboard → hover → **Record** / **Stop**, Service level) and loops the
recording full-screen (click **Demo**). Recordings are stored on the server
in `data/demo/` (not in git) as versioned files plus a pointer file
(`current.json`); the previous good version is kept as a fallback, older
ones and leftovers from interrupted uploads are cleaned up automatically.

### Requirements

- **Chromium / Chrome.** Recording the current tab uses
  `getDisplayMedia({ preferCurrentTab: true })`, which only Chromium
  supports. Playing the demo works in any browser.
- **Open the Pilot as `http://localhost:8000` on the Jetson**, not via its
  LAN IP. Browsers only allow screen capture in a secure context
  (`https://` or `localhost`); over plain `http://<ip>:8000` the Record entry
  is disabled with a message. Playing works over the network too.
- **For a trade fair, turn on Service → Customer demo → "Show Demo button for
  all users".** Service logins live only in memory and are gone after a page
  reload or kiosk restart; with the setting off, a logged-out screen can't see
  or play the demo, and a restart would fall back to the live screen. With it
  on, the screen comes back into the looping demo after a restart, and
  Record/Stop still need a Service login.
- Optional: install `ffmpeg` (`sudo apt install ffmpeg`). After each upload
  the server then remuxes the recording (stream copy, no re-encode) to add a
  full seek index. Without ffmpeg the server writes the video length into the
  file itself, which is enough for seeking in Chromium.

### Skipping the "Share this tab" prompt (optional)

Each time recording starts, Chromium asks once whether the page may share
this tab ("Share this tab" / "Diesen Tab teilen"); the Pilot shows a hint
next to the Demo button. On the kiosk this prompt can be skipped with
Chromium command-line switches:

| Switch | Effect |
| --- | --- |
| `--auto-accept-this-tab-capture` | Accepts the "share this tab" prompt of `preferCurrentTab` automatically. |
| `--auto-select-tab-capture-source-by-title="Produktionspilot"` | Alternative for the full picker: picks the tab whose title contains "Produktionspilot" (the Pilot's page title). |

**Not yet verified on the Jetson.** These are Chromium testing switches;
names were taken from the Chromium source, not tested against the Chromium
version installed on the Jetson. Check before relying on them:

1. `chromium-browser --version` (or `chromium --version`) on the Jetson.
2. Start the kiosk with the switch, e.g.

   ```
   chromium-browser --kiosk --auto-accept-this-tab-capture http://localhost:8000
   ```

3. Open `chrome://version` (in a normal window with the same flags) and check
   the switch appears under "Command Line".
4. Log in as Service, hover over Demo → Record: recording should start without
   a prompt. If the prompt still appears, the switch isn't supported by that
   version — recording still works, Wolfgang just clicks "Share this tab".

These switches apply to **every** page in that browser profile — only use them
for the kiosk browser that shows the Pilot on `localhost`, never for a
general-purpose browser.

### Limits

- Max 10 minutes per recording (auto-stop + save), max 500 MB.
- A page reload during recording ends it without saving; the current demo
  stays untouched (it is only switched after a new recording was uploaded and
  checked).
- If saving fails (e.g. the server was stopped), the recording stays in the
  browser with **Retry saving** and **Download recording**, and the message
  shows the real reason.
