import { writable, get } from 'svelte/store';
import { uploadDemoVideo } from './serviceApi.js';
import { demoStatus, showDemoMessage, formatClock, describeUploadError, isRetryableUploadError } from './demoMode.js';

// Records the CURRENT TAB (getDisplayMedia + preferCurrentTab) with
// MediaRecorder and uploads it as the demo when stopped. Module-level
// state, not component state: recording keeps running while the user
// moves between Dashboard / Statistics / Service (same tab, no reload).
//
// Every recording starts from a clean slate (previous stream stopped, new
// MediaRecorder, empty chunks, old download URL revoked). If saving fails,
// the recording is NOT lost: it stays in memory (phase 'failed') with
// "Retry saving" and "Download recording" until it is saved or a new
// recording replaces it. A page reload ends a recording without uploading
// anything, so the server's current demo is never touched by it.

// Safety limits (the backend enforces the same — production_pilot/demo_video.py).
export const MAX_DURATION_MS = 10 * 60 * 1000;
export const MAX_SIZE_BYTES = 500 * 1024 * 1024;
// Stop a little before the hard size limit so the finished file fits.
const SIZE_STOP_BYTES = MAX_SIZE_BYTES - 16 * 1024 * 1024;
const VIDEO_BITS_PER_SECOND = 4_000_000;
const FRAME_RATE = 30;
const CHUNK_MS = 1000;
const AUTO_RETRY_DELAY_MS = 2000;

// phase: 'idle' | 'prompt' (browser share dialog open) | 'recording' |
//        'saving' (progress 0..1) | 'failed' (error = { key, vars })
export const recorder = writable({ phase: 'idle', startedAt: null, progress: null, error: null });

let stream = null;
let mediaRecorder = null;
let chunks = [];
let bytes = 0;
let startedAt = 0;
let stopReason = 'user';
let limitTimer = null;
let pending = null; // { blob, durationSeconds, reason } — a recording not saved yet
let downloadUrl = null;

function setPhase(phase, extra = {}) {
  recorder.set({ phase, startedAt: null, progress: null, error: null, ...extra });
}

function pickMimeType() {
  const candidates = ['video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm'];
  return candidates.find((type) => MediaRecorder.isTypeSupported?.(type)) ?? '';
}

function releaseStream() {
  stream?.getTracks().forEach((track) => track.stop());
  stream = null;
}

function revokeDownloadUrl() {
  if (downloadUrl) URL.revokeObjectURL(downloadUrl);
  downloadUrl = null;
}

// Leaving/reloading the page while recording (or with an unsaved recording) loses it — warn.
function onBeforeUnload(event) {
  event.preventDefault();
}

export async function startRecording() {
  const phase = get(recorder).phase;
  if (phase !== 'idle' && phase !== 'failed') return;
  // Clean slate: a new recording replaces an unsaved one.
  pending = null;
  revokeDownloadUrl();
  releaseStream();
  mediaRecorder = null;
  chunks = [];
  bytes = 0;
  window.removeEventListener('beforeunload', onBeforeUnload);
  setPhase('prompt');

  try {
    stream = await navigator.mediaDevices.getDisplayMedia({
      video: { frameRate: { ideal: FRAME_RATE, max: FRAME_RATE } },
      audio: false,
      preferCurrentTab: true, // Chromium: offer just "share this tab"
      selfBrowserSurface: 'include',
      surfaceSwitching: 'exclude',
      monitorTypeSurfaces: 'exclude',
    });
  } catch (err) {
    setPhase('idle');
    if (err?.name === 'NotAllowedError' || err?.name === 'AbortError') showDemoMessage('demo_record_cancelled');
    else showDemoMessage('demo_record_failed', { error: `${err?.name ?? 'Error'}: ${err?.message ?? err}` });
    return;
  }

  try {
    const mimeType = pickMimeType();
    mediaRecorder = new MediaRecorder(stream, { ...(mimeType && { mimeType }), videoBitsPerSecond: VIDEO_BITS_PER_SECOND });
  } catch (err) {
    releaseStream();
    setPhase('idle');
    showDemoMessage('demo_record_failed', { error: `${err?.name ?? 'Error'}: ${err?.message ?? err}` });
    return;
  }

  const recorderForThisRun = mediaRecorder;
  stopReason = 'user';
  recorderForThisRun.ondataavailable = (event) => {
    if (!event.data?.size || recorderForThisRun !== mediaRecorder) return;
    chunks.push(event.data);
    bytes += event.data.size;
    if (bytes >= SIZE_STOP_BYTES) stopRecording('size');
  };
  recorderForThisRun.onstop = () => finish(recorderForThisRun);
  // The browser's own "Stop sharing" bar ends the capture -> save it.
  stream.getVideoTracks()[0]?.addEventListener('ended', () => stopRecording('user'));

  recorderForThisRun.start(CHUNK_MS);
  startedAt = performance.now();
  limitTimer = setTimeout(() => stopRecording('duration'), MAX_DURATION_MS);
  window.addEventListener('beforeunload', onBeforeUnload);
  setPhase('recording', { startedAt: Date.now() });
}

export function stopRecording(reason = 'user') {
  if (!mediaRecorder || mediaRecorder.state === 'inactive') return;
  stopReason = reason;
  mediaRecorder.stop(); // -> final dataavailable, then onstop -> finish()
}

function finish(stoppedRecorder) {
  if (stoppedRecorder !== mediaRecorder) return; // a stale recorder from an earlier run
  clearTimeout(limitTimer);
  const durationSeconds = Math.min((performance.now() - startedAt) / 1000, MAX_DURATION_MS / 1000);
  releaseStream();
  const blob = new Blob(chunks, { type: 'video/webm' });
  chunks = [];
  bytes = 0;
  mediaRecorder = null;
  if (!blob.size) {
    window.removeEventListener('beforeunload', onBeforeUnload);
    setPhase('idle');
    showDemoMessage('demo_save_failed_reason', { reason: 'empty recording' });
    return;
  }
  pending = { blob, durationSeconds, reason: stopReason };
  save(true);
}

async function save(autoRetry) {
  if (!pending) return;
  const job = pending;
  setPhase('saving', { progress: 0 });
  try {
    const status = await uploadDemoVideo(job.blob, job.durationSeconds, (p) =>
      recorder.update((r) => (r.phase === 'saving' ? { ...r, progress: p } : r)),
    );
    if (pending !== job) return;
    pending = null;
    revokeDownloadUrl();
    window.removeEventListener('beforeunload', onBeforeUnload);
    demoStatus.set({ ...status, loaded: true });
    setPhase('idle');
    const length = formatClock(status.duration_seconds ?? job.durationSeconds);
    const key = job.reason === 'duration' ? 'demo_autostop_duration' : job.reason === 'size' ? 'demo_autostop_size' : 'demo_saved';
    showDemoMessage(key, { length });
  } catch (err) {
    if (pending !== job) return;
    console.error('[demo] saving the recording failed:', err);
    if (autoRetry && isRetryableUploadError(err)) {
      await new Promise((resolve) => setTimeout(resolve, AUTO_RETRY_DELAY_MS));
      if (pending === job) save(false); // retry once automatically on a network error
      return;
    }
    setPhase('failed', { error: describeUploadError(err) }); // recording kept: Retry / Download
  }
}

/** "Retry saving" after a failed save (retries once more on a network error). */
export function retrySave() {
  if (get(recorder).phase === 'failed') save(true);
}

/** "Download recording": saves the unsaved recording as a file, as a fallback. */
export function downloadRecording() {
  if (!pending) return;
  revokeDownloadUrl();
  downloadUrl = URL.createObjectURL(pending.blob);
  const a = document.createElement('a');
  a.href = downloadUrl;
  a.download = `produktionspilot-demo-${new Date().toISOString().replace(/[:.]/g, '-')}.webm`;
  document.body.appendChild(a);
  a.click();
  a.remove();
}
