import { writable, get } from 'svelte/store';
import { startDemoUpload, uploadDemoChunk, finalizeDemoUpload } from './serviceApi.js';
import {
  demoStatus,
  loadDemoStatus,
  showDemoMessage,
  formatClock,
  describeUploadError,
  isRetryableUploadError,
} from './demoMode.js';

// Records the CURRENT TAB (getDisplayMedia + preferCurrentTab) with
// MediaRecorder. Module-level state, not component state: recording keeps
// running while the user moves between Dashboard / Statistics / Service
// (same tab, no reload).
//
// The recording is NOT held in browser memory: every CHUNK_MS the chunk is
// uploaded to the server (an upload session, appended in order to a temp
// file). Only chunks not sent yet stay in memory (failed chunks are retried
// a few times, then again with the next chunk). Stop sends the rest and
// finalizes on the server (validate, seek fix, atomic switch). If that
// fails, the file stays on the server and "Retry saving" retries the
// finalize. A page reload / lost connection never finalizes, so the
// current demo is untouched; the partial file is removed on the next start.
//
// The limits (max duration, warning, max size) come from the server
// (GET /api/demo/status) — production_pilot/demo_video.py defines them.

const VIDEO_BITS_PER_SECOND = 2_500_000;
const FRAME_RATE = 30;
const CHUNK_MS = 5000;
const CHUNK_RETRY_DELAYS_MS = [1000, 2000, 4000];
const AUTO_RETRY_DELAY_MS = 2000;
// Stop a little before the hard size limit so the finished file fits.
const SIZE_MARGIN_BYTES = 16 * 1024 * 1024;

// phase: 'idle' | 'prompt' (checks + browser share dialog) | 'recording'
//        (maxSeconds) | 'saving' (progress 0..1, null = finalizing) |
//        'failed' (error = { key, vars })
export const recorder = writable({ phase: 'idle', startedAt: null, maxSeconds: null, progress: null, error: null });

let stream = null;
let mediaRecorder = null;
let startedAt = 0;
let stopReason = 'user';
let limitTimer = null;
let warnTimer = null;
// The upload of the current / unsaved recording:
// { id, queue: Blob[], sentBytes, queuedBytes, pumping, error, stopAtBytes,
//   maxSeconds, durationSeconds, reason }
let session = null;

function setPhase(phase, extra = {}) {
  recorder.set({ phase, startedAt: null, maxSeconds: null, progress: null, error: null, ...extra });
}

function pickMimeType() {
  const candidates = ['video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm'];
  return candidates.find((type) => MediaRecorder.isTypeSupported?.(type)) ?? '';
}

function releaseStream() {
  stream?.getTracks().forEach((track) => track.stop());
  stream = null;
}

function clearTimers() {
  clearTimeout(limitTimer);
  clearTimeout(warnTimer);
  limitTimer = warnTimer = null;
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// Leaving/reloading the page while recording (or with an unsaved recording) loses it — warn.
function onBeforeUnload(event) {
  event.preventDefault();
}

function errorText(err) {
  return `${err?.name ?? 'Error'}: ${err?.message ?? err}`;
}

/** The limits from the server (loaded once if the status isn't there yet). */
async function serverLimits() {
  if (!get(demoStatus).max_duration_seconds) await loadDemoStatus();
  const status = get(demoStatus);
  if (!status.max_duration_seconds) throw new Error('Server not reachable');
  return status;
}

// --- chunk upload -------------------------------------------------------------

function progressOf(job) {
  const total = job.sentBytes + job.queuedBytes;
  return total ? job.sentBytes / total : 1;
}

async function sendChunk(job, blob) {
  for (let attempt = 0; ; attempt++) {
    try {
      await uploadDemoChunk(job.id, job.sentBytes, blob);
      return;
    } catch (err) {
      const retryable = isRetryableUploadError(err) || err?.status >= 500;
      if (!retryable || attempt >= CHUNK_RETRY_DELAYS_MS.length) throw err;
      await sleep(CHUNK_RETRY_DELAYS_MS[attempt]);
    }
  }
}

async function drain(job) {
  try {
    while (job.queue.length && session === job) {
      const blob = job.queue[0];
      await sendChunk(job, blob);
      job.queue.shift();
      job.sentBytes += blob.size;
      job.queuedBytes -= blob.size;
      job.error = null;
      recorder.update((r) => (r.phase === 'saving' ? { ...r, progress: progressOf(job) } : r));
    }
  } catch (err) {
    job.error = err; // chunks stay queued; the next chunk / Stop tries again
    console.error('[demo] uploading a chunk failed:', err);
  }
}

/** Sends the queued chunks in order; one sender at a time per session. */
function pump(job) {
  if (!job.pumping) job.pumping = drain(job).finally(() => (job.pumping = null));
  return job.pumping;
}

// --- recording ----------------------------------------------------------------

export async function startRecording() {
  const phase = get(recorder).phase;
  if (phase !== 'idle' && phase !== 'failed') return;
  // Clean slate: a new recording replaces an unsaved one (the server removes its file).
  session = null;
  clearTimers();
  releaseStream();
  mediaRecorder = null;
  window.removeEventListener('beforeunload', onBeforeUnload);
  setPhase('prompt');

  let limits;
  let sessionId;
  try {
    limits = await serverLimits();
    ({ session_id: sessionId } = await startDemoUpload()); // also checks the free disk space
  } catch (err) {
    setPhase('idle');
    if (err?.status === 507) showDemoMessage('demo_disk_full', { detail: err.message.replace(/^HTTP 507: /, '') }, 20000);
    else showDemoMessage('demo_record_failed', { error: errorText(err) });
    return;
  }

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
    else showDemoMessage('demo_record_failed', { error: errorText(err) });
    return;
  }

  try {
    const mimeType = pickMimeType();
    mediaRecorder = new MediaRecorder(stream, { ...(mimeType && { mimeType }), videoBitsPerSecond: VIDEO_BITS_PER_SECOND });
  } catch (err) {
    releaseStream();
    setPhase('idle');
    showDemoMessage('demo_record_failed', { error: errorText(err) });
    return;
  }

  const maxSeconds = limits.max_duration_seconds;
  const warnSeconds = limits.duration_warning_seconds;
  const job = {
    id: sessionId,
    queue: [],
    sentBytes: 0,
    queuedBytes: 0,
    pumping: null,
    error: null,
    stopAtBytes: limits.max_size_bytes - SIZE_MARGIN_BYTES,
    maxSeconds,
    durationSeconds: 0,
    reason: 'user',
  };
  session = job;

  const recorderForThisRun = mediaRecorder;
  stopReason = 'user';
  recorderForThisRun.ondataavailable = (event) => {
    if (!event.data?.size || recorderForThisRun !== mediaRecorder || session !== job) return;
    job.queue.push(event.data);
    job.queuedBytes += event.data.size;
    pump(job);
    if (job.sentBytes + job.queuedBytes >= job.stopAtBytes) stopRecording('size');
  };
  recorderForThisRun.onstop = () => finish(recorderForThisRun, job);
  // The browser's own "Stop sharing" bar ends the capture -> save it.
  stream.getVideoTracks()[0]?.addEventListener('ended', () => stopRecording('user'));

  recorderForThisRun.start(CHUNK_MS);
  startedAt = performance.now();
  limitTimer = setTimeout(() => stopRecording('duration'), maxSeconds * 1000);
  if (warnSeconds > 0 && warnSeconds < maxSeconds) {
    warnTimer = setTimeout(
      () => showDemoMessage('demo_autostop_warning', { minutes: Math.round(warnSeconds / 60) }, warnSeconds * 1000),
      (maxSeconds - warnSeconds) * 1000,
    );
  }
  window.addEventListener('beforeunload', onBeforeUnload);
  setPhase('recording', { startedAt: Date.now(), maxSeconds });
}

export function stopRecording(reason = 'user') {
  if (!mediaRecorder || mediaRecorder.state === 'inactive') return;
  stopReason = reason;
  mediaRecorder.stop(); // -> final dataavailable, then onstop -> finish()
}

function finish(stoppedRecorder, job) {
  if (stoppedRecorder !== mediaRecorder || session !== job) return; // a stale recorder from an earlier run
  clearTimers();
  job.durationSeconds = Math.min((performance.now() - startedAt) / 1000, job.maxSeconds);
  job.reason = stopReason;
  releaseStream();
  mediaRecorder = null;
  if (!job.sentBytes && !job.queuedBytes) {
    session = null;
    window.removeEventListener('beforeunload', onBeforeUnload);
    setPhase('idle');
    showDemoMessage('demo_save_failed_reason', { reason: 'empty recording' });
    return;
  }
  save(job, true);
}

async function save(job, autoRetry) {
  if (session !== job) return;
  setPhase('saving', { progress: progressOf(job) });
  try {
    // Send what is still queued (each chunk with its own retries).
    while (job.queue.length) {
      job.error = null;
      await pump(job);
      if (session !== job) return;
      if (job.error && job.queue.length) throw job.error;
    }
    recorder.update((r) => (r.phase === 'saving' ? { ...r, progress: null } : r)); // finalizing on the server
    const status = await finalizeDemoUpload(job.id, job.durationSeconds);
    if (session !== job) return;
    session = null;
    window.removeEventListener('beforeunload', onBeforeUnload);
    demoStatus.set({ ...status, loaded: true });
    setPhase('idle');
    const length = formatClock(status.duration_seconds ?? job.durationSeconds);
    const key = job.reason === 'duration' ? 'demo_autostop_duration' : job.reason === 'size' ? 'demo_autostop_size' : 'demo_saved';
    showDemoMessage(key, { length, minutes: Math.round(job.maxSeconds / 60) });
  } catch (err) {
    if (session !== job) return;
    console.error('[demo] saving the recording failed:', err);
    if (autoRetry && isRetryableUploadError(err)) {
      await sleep(AUTO_RETRY_DELAY_MS);
      if (session === job) save(job, false); // retry once automatically on a network error
      return;
    }
    setPhase('failed', { error: describeUploadError(err) }); // file kept on the server: Retry saving
  }
}

/** "Retry saving" after a failed save: sends any unsent chunks, then retries the finalize step. */
export function retrySave() {
  if (get(recorder).phase === 'failed' && session) save(session, true);
}
