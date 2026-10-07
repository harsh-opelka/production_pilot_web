// Plain-assert self-test for stateColors.js — hex validation, the automatic
// white/dark text colour, the low-contrast check, the "too similar" warning
// and the HSV maths behind the free picker. No test runner needed:
//
//     node frontend/tests/stateColors.test.mjs

const {
  normalizeHex,
  bestText,
  bestTextColor,
  contrastRatio,
  colorDistance,
  findSimilarPairs,
  stateColorVars,
  hexToHsv,
  hsvToHex,
  MIN_CONTRAST,
  SIMILAR_COLOR_DELTA_E,
  TEXT_LIGHT,
  TEXT_DARK,
} = await import('../src/lib/stateColors.js');

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

// Hex validation / normalization.
check('#rgb -> #RRGGBB uppercase', normalizeHex('#0af'), '#00AAFF');
check('lowercase #rrggbb -> uppercase', normalizeHex('#05346c'), '#05346C');
check('spaces trimmed (pasted value)', normalizeHex(' #facc15 '), '#FACC15');
for (const bad of ['05346C', '#12', '#12345', '#1234567', '#GGGGGG', '', null, 42, 'red']) {
  check(`invalid -> null: ${JSON.stringify(bad)}`, normalizeHex(bad), null);
}

// Automatic text colour.
check('yellow (Hot) -> dark text', bestTextColor('#FACC15'), TEXT_DARK);
check('OPELKA navy (Waiting) -> white text', bestTextColor('#05346C'), TEXT_LIGHT);
check('light red -> dark text', bestTextColor('#FCA5A5'), TEXT_DARK);
check('orange (Heating) -> dark text', bestTextColor('#F59E0B'), TEXT_DARK);
check('red (Error) -> white text', bestTextColor('#DC2626'), TEXT_LIGHT);
check('white on black is 21:1', Math.round(contrastRatio('#FFFFFF', '#000000')), 21);
check('navy reaches 4.5:1 with its best text', bestText('#05346C').ratio >= MIN_CONTRAST, true);
// Mid grey: the best of white/dark still falls short -> Service shows a warning.
check('mid grey #777777 stays below 4.5:1 -> warning', bestText('#777777').ratio < MIN_CONTRAST, true);

// Similar colours.
check('threshold is a named constant (ΔE 18)', SIMILAR_COLOR_DELTA_E, 18);
check('near-identical colours are ~0 apart', colorDistance('#16A34A', '#17A44B') < 1, true);
check('two near-identical state colours -> warning',
  findSimilarPairs({ baking: '#16A34A', near_completion: '#17A44B', error: '#DC2626' }), [['baking', 'near_completion']]);
check('green vs darker green -> warning',
  findSimilarPairs({ baking: '#16A34A', near_completion: '#15803D' }), [['baking', 'near_completion']]);
check('clearly different colours -> no warning',
  findSimilarPairs({ baking: '#16A34A', near_completion: '#9333EA', hot: '#FACC15', error: '#DC2626' }), []);
check('Cold and the Standby/Unknown fallback may share a grey (no warning)',
  findSimilarPairs({ cold: '#6B7280', standby: '#6B7280' }), []);

// CSS variables.
check('stateColorVars: background + automatic text colour, CSS slot names',
  stateColorVars({ near_completion: '#facc15', waiting: '#05346C', bogus: '#000000' }),
  {
    '--state-waiting': '#05346C',
    '--state-waiting-fg': TEXT_LIGHT,
    '--state-near-completion': '#FACC15',
    '--state-near-completion-fg': TEXT_DARK,
  });

// HSV round trip (free picker).
for (const hex of ['#05346C', '#FACC15', '#DC2626', '#6B7280', '#FFFFFF', '#000000']) {
  check(`HSV round trip ${hex}`, hsvToHex(hexToHsv(hex)), hex);
}

console.log();
console.log(allPassed ? 'ALL PASSED' : 'SOME FAILED');
process.exit(allPassed ? 0 : 1);
