// Plain-assert self-test for demoMode.js — Customer Demo Mode's pure rules:
// remembering Live/Demo mode (also when localStorage is missing or
// throws), which Demo menu entries are enabled, who sees the button, the
// secure-context check for recording, and the video URL. No test runner:
//
//     node frontend/tests/demoMode.test.mjs

const {
  loadMode,
  saveMode,
  MODE_STORAGE_KEY,
  menuEntries,
  recordSupport,
  demoButtonVisible,
  canManageDemo,
  formatClock,
  demoVideoUrl,
  describeUploadError,
  isRetryableUploadError,
  nextPlaybackSource,
} = await import('../src/lib/demoMode.js');
const { UploadNetworkError, ServiceApiError } = await import('../src/lib/serviceApi.js');

let allPassed = true;

function check(label, actual, want) {
  const ok = JSON.stringify(actual) === JSON.stringify(want);
  allPassed &&= ok;
  console.log(`[${ok ? 'PASS' : 'FAIL'}] ${label}`);
  if (!ok) {
    console.log(`         expected: ${JSON.stringify(want)}`);
    console.log(`         actual:   ${JSON.stringify(actual)}`);
  }
}

function memoryStorage(initial = {}) {
  const data = { ...initial };
  return { getItem: (k) => (k in data ? data[k] : null), setItem: (k, v) => (data[k] = String(v)), data };
}
const throwing = {
  getItem() {
    throw new Error('SecurityError: storage blocked');
  },
  setItem() {
    throw new Error('QuotaExceededError');
  },
};

// Mode persistence.
const mem = memoryStorage();
check('nothing stored -> live', loadMode(mem), 'live');
saveMode('demo', mem);
check('saved demo -> demo after a reload', [mem.data[MODE_STORAGE_KEY], loadMode(mem)], ['demo', 'demo']);
saveMode('live', mem);
check('saved live -> live', loadMode(mem), 'live');
check('junk value -> live', loadMode(memoryStorage({ [MODE_STORAGE_KEY]: 'party' })), 'live');
check('storage throws -> live, no crash', loadMode(throwing), 'live');
let threw = false;
try {
  saveMode('demo', throwing);
} catch {
  threw = true;
}
check('saving into throwing storage does not crash', threw, false);
check('no storage at all -> live', loadMode(null), 'live');

// Menu entries per state (support ok).
const ok = { ok: true, reasonKey: null };
check('idle: Record on, Stop off', menuEntries('idle', ok), { record: { enabled: true, reasonKey: null }, stop: { enabled: false } });
check('recording: Record off, Stop on', menuEntries('recording', ok), { record: { enabled: false, reasonKey: null }, stop: { enabled: true } });
check('browser prompt open: both off', menuEntries('prompt', ok), { record: { enabled: false, reasonKey: null }, stop: { enabled: false } });
check('saving: both off', menuEntries('saving', ok), { record: { enabled: false, reasonKey: null }, stop: { enabled: false } });
check('save failed (recording kept): Record allowed again, Stop off',
  menuEntries('failed', ok), { record: { enabled: true, reasonKey: null }, stop: { enabled: false } });

// Secure context / support detection.
const chromium = { isSecureContext: true, navigator: { mediaDevices: { getDisplayMedia() {} } }, MediaRecorder: function () {} };
check('localhost / https in Chromium -> recording available', recordSupport(chromium), { ok: true, reasonKey: null });
const remoteHttp = { ...chromium, isSecureContext: false, navigator: { mediaDevices: undefined } };
check('remote http://<ip>:8000 -> disabled with the secure-context message', recordSupport(remoteHttp),
  { ok: false, reasonKey: 'demo_record_insecure' });
check('... and the menu shows Record disabled with that reason', menuEntries('idle', recordSupport(remoteHttp)).record,
  { enabled: false, reasonKey: 'demo_record_insecure' });
check('secure but no tab capture (other browser) -> unsupported message',
  recordSupport({ isSecureContext: true, navigator: {}, MediaRecorder: undefined }), { ok: false, reasonKey: 'demo_record_unsupported' });

// Who sees what.
check('Demo button: Service always, others only with the setting',
  [demoButtonVisible('service', false), demoButtonVisible('management', false), demoButtonVisible(null, false), demoButtonVisible(null, true)],
  [true, false, false, true]);
check('Record/Stop: Service only', [canManageDemo('service'), canManageDemo('management'), canManageDemo(null)], [true, false, false]);

// Formatting / URL.
check('clock mm:ss', [formatClock(42), formatClock(600), formatClock(NaN)], ['00:42', '10:00', '00:00']);
check('video URL is versioned (+ token when logged in, + which=previous for the fallback)',
  [demoVideoUrl({ version: 'demo-1.webm' }, null), demoVideoUrl({ version: 'demo-1.webm' }, 'abc'),
   demoVideoUrl({ version: 'demo-1.webm' }, null, 'previous')],
  ['/api/demo/video?v=demo-1.webm', '/api/demo/video?v=demo-1.webm&token=abc', '/api/demo/video?v=demo-1.webm&which=previous']);

// Upload errors: the real reason, not just "Failed to fetch".
check('no response at all -> network error key, retried automatically once',
  [describeUploadError(new UploadNetworkError('network')), isRetryableUploadError(new UploadNetworkError('network'))],
  [{ key: 'demo_upload_network', vars: {} }, true]);
check('timeout -> timeout key', describeUploadError(new UploadNetworkError('timeout')), { key: 'demo_upload_timeout', vars: {} });
check('HTTP error -> status + server message, not retried automatically',
  [describeUploadError(new ServiceApiError('HTTP 413: Recording larger than 500 MB', 413)),
   isRetryableUploadError(new ServiceApiError('HTTP 413: x', 413))],
  [{ key: 'demo_upload_http', vars: { detail: 'HTTP 413: Recording larger than 500 MB' } }, false]);
check('401 -> log in again, then retry', describeUploadError(new ServiceApiError('HTTP 401: Not authenticated', 401)).key, 'demo_upload_auth');
check('anything else -> name and message', describeUploadError(new TypeError('boom')),
  { key: 'demo_upload_other', vars: { detail: 'TypeError: boom' } });

// Player fallback.
check('newest fails and a previous version exists -> play previous', nextPlaybackSource('current', { has_previous: true }), 'previous');
check('newest fails, no previous -> give up (Live)', nextPlaybackSource('current', { has_previous: false }), null);
check('previous fails too -> give up (Live)', nextPlaybackSource('previous', { has_previous: true }), null);

console.log();
console.log(allPassed ? 'ALL PASSED' : 'SOME FAILED');
process.exit(allPassed ? 0 : 1);
