// Plain-assert self-test for nextAction.describeNextAction() — the Next
// Action banner text/colour and the NEXT badge's tile (its `ip`), in both
// languages — plus the tile formatters in format.js (temperature, recipe,
// heating fill level). No test runner needed:
//
//     node frontend/tests/nextAction.test.mjs
//
// WHICH machine is chosen is decided on the backend
// (production_pilot/priority.select_next_action — see test_priority.py);
// the inputs here are that function's possible outputs.

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

const { describeNextAction } = await import('../src/lib/nextAction.js');
const { formatTemperature, formatRecipe, heatingFillLevel } = await import('../src/lib/format.js');

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

function checkAction(label, nextAction, expected) {
  for (const [language, text] of Object.entries(expected.text)) {
    check(`${label} (${language})`, describeNextAction(nextAction, language), {
      text,
      tier: expected.tier,
      ip: expected.ip,
      allBaking: expected.allBaking ?? false,
    });
  }
}

const pick = (kind, n) => ({ kind, ip: `10.0.0.${n}`, unit_number: n });

checkAction('Error -> Check Error', pick('error', 2), {
  text: { en: '2: Check Error', de: '2: Störung prüfen' },
  tier: 'error',
  ip: '10.0.0.2',
});
checkAction('Waiting -> Load Machine', pick('load', 3), {
  text: { en: '3: Load Machine', de: '3: Beladen' },
  tier: 'load',
  ip: '10.0.0.3',
});
checkAction('Hot -> Switch to Auto', pick('switch_to_auto', 1), {
  text: { en: '1: Switch to Auto', de: '1: Auf Auto stellen' },
  tier: 'hot',
  ip: '10.0.0.1',
});
checkAction('Almost finished -> Unload Soon', pick('unload_soon', 4), {
  text: { en: '4: Unload Soon', de: '4: Bald entladen' },
  tier: 'near-completion',
  ip: '10.0.0.4',
});
checkAction('All baking -> smiley flag, no NEXT badge', { kind: 'all_baking', ip: null, unit_number: null }, {
  text: { en: '–', de: '–' },
  tier: 'none',
  ip: null,
  allBaking: true,
});
checkAction('Nothing actionable -> dash, no smiley', { kind: 'none', ip: null, unit_number: null }, {
  text: { en: '–', de: '–' },
  tier: 'none',
  ip: null,
});
checkAction('No payload yet (before the first WS message) -> dash', undefined, {
  text: { en: '–', de: '–' },
  tier: 'none',
  ip: null,
});

check('temperature: current / target, rounded', formatTemperature(29.4, 20), '29 / 20 °C');
check('temperature: missing target', formatTemperature(180.6, null), '181 / — °C');
check('temperature: both missing -> dash', formatTemperature(null, null), '—');
check('recipe: empty -> dash', formatRecipe(''), '—');
check('recipe: name shown as-is', formatRecipe('Spritzkuchen'), 'Spritzkuchen');

// Heating fill level (FryerTile's rising oil level).
check('fill: 29.4 / 180', Math.round(heatingFillLevel(29.4, 180) * 1000) / 1000, 0.163);
check('fill: 180 / 180 -> full', heatingFillLevel(180, 180), 1);
check('fill: current above target -> clamped to 1', heatingFillLevel(195, 180), 1);
check('fill: negative current -> clamped to 0', heatingFillLevel(-5, 180), 0);
check('fill: current None -> no fill', heatingFillLevel(null, 180), null);
check('fill: target None -> no fill', heatingFillLevel(29.4, null), null);
check('fill: target 0 -> no fill', heatingFillLevel(29.4, 0), null);

// Floor layout geometry (natural size; shifted back, never shrunk).
const { placeInArea, findOverlaps, naturalGroupSize } = await import('../src/lib/floorLayout.js');
const quattro = naturalGroupSize(4, 'horizontal');
check('QUATTRO at 1080p matches the page (measured on the page: 1051 x 313 px)',
  [Math.round(quattro.w), Math.round(quattro.h)], [1051, 313]);
check('placed at its % position when it fits', placeInArea(10, 10, 200, 100, 1000, 500), { left: 100, top: 50 });
check('past the right/bottom edge -> shifted back, same size', placeInArea(90, 90, 200, 100, 1000, 500), { left: 800, top: 400 });
check('bigger than the area -> pinned to 0', placeInArea(50, 50, 1200, 100, 1000, 500), { left: 0, top: 250 });
check('overlap detected', findOverlaps([{ label: 'A', left: 0, top: 0, w: 10, h: 10 }, { label: 'B', left: 5, top: 5, w: 10, h: 10 }]), [['A', 'B']]);
check('touching edges are not an overlap', findOverlaps([{ label: 'A', left: 0, top: 0, w: 10, h: 10 }, { label: 'B', left: 10, top: 0, w: 10, h: 10 }]), []);

console.log();
console.log(allPassed ? 'ALL PASSED' : 'SOME FAILED');
process.exit(allPassed ? 0 : 1);
