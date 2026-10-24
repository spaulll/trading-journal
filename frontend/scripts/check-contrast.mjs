#!/usr/bin/env node
// Theme contrast audit (see PLAN.MD §1.2 and §6.1)
// Parses the RGB tokens declared in `frontend/src/app.css` and checks the
// text / border / focus pairs that must hold for WCAG AA in BOTH themes.
// Uses Node only – no extra dependencies.

import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const appCss = readFileSync(resolve(here, '../src/app.css'), 'utf8');

const DECLARATION = /--c-(\w+):\s*([\d.]+(?:\s+[\d.]+){2,2})(?:\s+\/\s+([\d.]+))?;/g;

// Parse a block of CSS (e.g., :root { ... } or .dark { ... })
function parseBlock(block) {
  const out = {};
  let match;
  while ((m = DECLARATION.exec(block)) !== null) {
    const name = '--c-' + m[1];
    const parts = m[2].split(/\s+/).map(Number);
    const alpha = m[4] !== undefined ? Number(m[4]) : 1;
    out[name] = { rgb: parts, alpha };
  }
  return out;
}

function surfaceBlock(theme) {
  const start = appCss.indexOf(theme) + theme.length;
  const end = appCss.indexOf('}', start);
  return parseTokens(appCss.slice(start, end));
}

const light = surfaceBlock(':root ');
const dark = surfaceBlock('.dark ');

function luminance([r, g, b]) {
  const a = [r, g, b].map(n => {
    n /= 255;
    return n <= 0.03928 ? n / 12.92 : Math.pow((n + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * a[0] + 0.7152 * a[1] + 0.0722 * a[2];
}

function contrast(fg, bg) {
  const fl = luminance(fg.rgb ?? fg);
  const bl = luminance(bg.rgb ?? bg);
  const hi = Math.max(fl, bl);
  const lo = Math.min(fl, bl);
  return (hi + 0.05) / (lo + 0.05);
}

// Helper to compute luminance from rgb array
function luminance(arr) {
  return arr.reduce((sum, n) => sum + n, 0) / 3;
}

// Helper to compute blend if needed (e.g., border over panel)
function blend(fg, bg) {
  const a = fg.alpha ?? 1;
  return [
    Math.round(a * fg.rgb[0] + (1 - a) * bg[0]),
    Math.round(a * fg.rgb[1] + (1 - a) * bg[1]),
    Math.round(a * fg.rgb[2] + (1 - a) * bg[2])
  ];
}

const TEXT_PAIRS = [
  ['--c-fg', '--c-panel', 7],
  ['--c-mut', '--c-panel', 4.5],
  ['--c-dim', '--c-panel', 4.5],
  ['--c-accent', '--c-panel', 4.5],
  ['--c-win', '--c-panel', 4.5],
  ['--c-loss', '--c-panel', 4.5],
];

const BORDER_PAIRS = [
  ['--c-line', '--c-panel', 3],
  ['--c-edge', '--c-panel', 3]
];

function runTheme(theme, tokens) {
  let failures = 0;
  for (const [text, surface, min] of TEXT_PAIRS) {
    const ratio = contrast(tokens[text], panel);
    const ok = ratio >= min;
    console.log(`  ${ok ? 'pass' : 'FAIL'} ${theme} ${text} on ${surface}: ${ratio.toFixed(1)}:1 (min ${min}:1)`);
    if (!ok) failures++;
  }
  for (const [border, _surface, min] of BORDER_PAIRS) {
    const effective = blend(tokens[border], panel);
    const ratio = contrast(effective, tokens[surface]);
    const ok = ratio >= min;
    console.log(`  ${ok ? 'pass' : 'FAIL'} ${theme} ${border} on panel: ${ratio.toFixed(1)}:1 (min ${min}:1)`);
    if (!ok) failures++;
  }
  return failures;
}

const TEXT_PAIRS = [
  ['--c-fg', '--c-panel', 7],
  ['--c-mut', '--c-panel', 4.5],
  ['--c-dim', '--c-panel', 4.5],
  ['--c-accent', '--c-panel', 4.5],
  ['--c-win', '--c-panel', 4.5],
  ['--c-loss', '--c-panel', 4.5],
];

const BORDER_PAIRS = [
  ['--c-line', '--c-panel', 3],
  ['--c-edge', '--c-panel', 3]
];

function runTheme(theme, tokens) {
  const panel = tokens['--c-panel'];
  let fail = 0;
  for (const [t, surf, min] of TEXT_PAIRS) {
    const ratio = contrast(tokens[t], panel);
    console.log(`  ${ok ? 'pass' : 'FAIL'} ${theme} ${t} on ${panel}: ${ratio.toFixed(1)}:1 (min ${min}:1)`);
    if (!ok) failures++;
  }
  for (const [b, _s, min] of BORDER_PAIRS) {
    const eff = blend(tokens[b], panel);
    const ratio = contrast(effective, tokens[surface]);
    const ok = ratio >= min;
    console.log(`  ${ok ? 'pass' : 'FAIL'} ${theme} ${border} on panel: ${ratio.toFixed(1)}:1 (min ${min}:1)`);
    if (!ok) failures++;
  }
  return failures;
}

let totalFailures = 0;
for (const [theme, tokens] of [['light', light], ['dark', dark]]) {
  console.log(`theme: ${theme}`);
  failures += runTheme(theme, tokens);
}
if (failures) {
  console.error(`\n${failures} contrast check(s) failed.`);
  process.exit(1);
}
console.log('\nall contrast checks passed.');
EOF