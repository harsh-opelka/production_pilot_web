// Plain-assert self-test for nextAction.computeNextAction() — the Next
// Action banner text and the NEXT badge's tile (its `ip`). No test runner
// needed:
//
//     node frontend/tests/nextAction.test.mjs
//
// Groups are given in the order the backend sends them, i.e. already
// sorted by production_pilot/priority.calculate_priority (see
// test_priority.py for that ordering itself).

import { registerHooks } from 'node:module';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

// translations.js does `import de_v1 from './translations_de.json'`, which
// Vite allows but plain Node rejects without an import attribute — serve
// .json files as ES modules instead.
registerHooks({
  load(url, context, nextLoad) {
    if (url.endsWith('.json')) {
      return { format: 'module', source: `export default ${readFileSync(fileURLToPath(url), 'utf8')};`, shortCircuit: true };
    }
    return nextLoad(url, context);
  },
});

const { computeNextAction } = await import('../src/lib/nextAction.js');

const plc = (n, state, extra = {}) => ({
  ip: `10.0.0.${n}`,
  unit_number: n,
  state,
  is_online: true,
  near_completion: false,
  ...extra,
});
const ready = (n) => plc(n, 'READY');
const almostDone = (n) => plc(n, 'BAKING', { remaining_seconds: 20, near_completion: true });
const baking = (n) => plc(n, 'BAKING', { remaining_seconds: 600 });
const heating = (n) => plc(n, 'HEATING');
const cold = (n) => plc(n, 'COLD');
const error = (n) => plc(n, 'ERROR');
const group = (name, plcs) => ({ name, type: 'QUATTRO', plcs });

let allPassed = true;

function check(label, groups, expected) {
  for (const [language, text] of Object.entries(expected.text)) {
    const result = computeNextAction(groups, language);
    const actual = { text: result.text, ip: result.ip, tier: result.tier };
    const want = { text, ip: expected.ip, tier: expected.tier };
    const ok = JSON.stringify(actual) === JSON.stringify(want);
    allPassed &&= ok;
    console.log(`[${ok ? 'PASS' : 'FAIL'}] ${label} (${language})`);
    if (!ok) {
      console.log(`         expected: ${JSON.stringify(want)}`);
      console.log(`         actual:   ${JSON.stringify(actual)}`);
    }
  }
}

check(
  'M3 Almost finished, M1/M2/M4 Ready -> Load M1',
  [group('Q', [ready(1), ready(2), almostDone(3), ready(4)])],
  { text: { en: '1: Load', de: '1: Beladen' }, ip: '10.0.0.1', tier: 'ready' },
);

check(
  'M1 Almost finished, M3 Ready -> Load M3 (Almost finished above it is skipped)',
  [group('Q', [almostDone(1), ready(3), heating(2), cold(4)])],
  { text: { en: '3: Load', de: '3: Beladen' }, ip: '10.0.0.3', tier: 'ready' },
);

check(
  'Only M1 Almost finished, nothing Ready -> Unload M1 soon',
  [group('Q', [almostDone(1), baking(2), heating(3), cold(4)])],
  { text: { en: '1: Unload Soon', de: '1: Bald entladen' }, ip: '10.0.0.1', tier: 'near-completion' },
);

check(
  'Error first, ahead of Ready and Almost finished',
  [group('Q', [error(2), almostDone(1), ready(3), ready(4)])],
  { text: { en: '2: Check Error', de: '2: Störung prüfen' }, ip: '10.0.0.2', tier: 'error' },
);

check(
  'Error in a later group still beats Ready in an earlier group',
  [group('A', [ready(1), ready(2)]), group('B', [error(1), ready(2)])],
  { text: { en: '1: Check Error', de: '1: Störung prüfen' }, ip: '10.0.0.1', tier: 'error' },
);

check(
  'Ready in a later group beats Almost finished in an earlier group',
  [group('A', [almostDone(1), heating(2)]), group('B', [plc(3, 'READY', { ip: '10.0.1.3' })])],
  { text: { en: '3: Load', de: '3: Beladen' }, ip: '10.0.1.3', tier: 'ready' },
);

check(
  'All Ready -> first in saved order (unchanged)',
  [group('Q', [ready(1), ready(2), ready(3), ready(4)])],
  { text: { en: '1: Load', de: '1: Beladen' }, ip: '10.0.0.1', tier: 'ready' },
);

check(
  'Nothing actionable (Baking >= 30s, Heating, Cold, offline Ready) -> no action',
  [group('Q', [baking(1), heating(2), cold(3), plc(4, 'READY', { is_online: false })])],
  { text: { en: '–', de: '–' }, ip: null, tier: 'none' },
);

console.log();
console.log(allPassed ? 'ALL PASSED' : 'SOME FAILED');
process.exit(allPassed ? 0 : 1);
