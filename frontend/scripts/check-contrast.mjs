#!/usr/bin/env node
// Theme contrast audit (see PLAN.MD §1.2 and §6.1)
// Parses the RGB tokens declared in `frontend/src/app.css` and checks the
// text / hairline pairs that must hold in BOTH themes.
// Uses Node only – no extra dependencies.

import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const appCss = readFileSync(resolve(here, '../src/app.css'), 'utf8');

const TOKEN_RE = /--c-([\w-]+):\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)(?:\s*\/\s*([\d.]+))?;/g;

function parseTokens(block) {
  const out = {};
  for (const match of block.matchAll(TOKEN_RE)) {
    out[`--c-${match[1]}`] = {
      rgb: [Number(match[2]), Number(match[3]), Number(match[4])],
      alpha: match[5] === undefined ? 1 : Number(match[5])
    };
  }
  return out;
}

function surfaceBlock(selector) {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = new RegExp(`${escaped}\\s*\\{`, 'm').exec(appCss);
  if (!match) throw new Error(`Could not find ${selector} in src/app.css`);
  const start = match.index + match[0].length;
  const end = appCss.indexOf('}', start);
  return parseTokens(appCss.slice(start, end));
}

const themes = {
  light: surfaceBlock(':root'),
  dark: surfaceBlock('.dark')
};

function luminance([r, g, b]) {
  const channels = [r, g, b].map((n) => {
    n /= 255;
    return n <= 0.03928 ? n / 12.92 : Math.pow((n + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

function contrast(fg, bg) {
  const fgLum = luminance(fg.rgb ?? fg);
  const bgLum = luminance(bg.rgb ?? bg);
  const hi = Math.max(fgLum, bgLum);
  const lo = Math.min(fgLum, bgLum);
  return (hi + 0.05) / (lo + 0.05);
}

function blend(fg, bg) {
  const alpha = fg.alpha ?? 1;
  return fg.rgb.map((channel, index) =>
    Math.round(alpha * channel + (1 - alpha) * bg.rgb[index])
  );
}

const SURFACES = ['--c-panel', '--c-raised', '--c-overlay'];
const TEXT_PAIRS = [
  ['--c-fg', 7],
  ['--c-mut', 4.5],
  ['--c-dim', 4.5],
  ['--c-accent', 4.5],
  ['--c-win', 4.5],
  ['--c-loss', 4.5]
];
// Hairlines are deliberately quiet; this is a visibility floor, not the 3:1
// non-text target. Component-level contrast is covered by the Phase 6 audit.
const BORDER_PAIRS = [
  ['--c-line', 1.15],
  ['--c-edge', 1.15]
];

function token(tokens, name, theme) {
  const value = tokens[name];
  if (!value) throw new Error(`Missing ${name} in the ${theme} theme`);
  return value;
}

function runTheme(theme, tokens) {
  let failures = 0;

  for (const surfaceName of SURFACES) {
    const surface = token(tokens, surfaceName, theme);
    for (const [textName, min] of TEXT_PAIRS) {
      const ratio = contrast(token(tokens, textName, theme), surface);
      const ok = ratio >= min;
      console.log(
        `  ${ok ? 'pass' : 'FAIL'} ${theme} ${textName} on ${surfaceName}: ${ratio.toFixed(1)}:1 (min ${min}:1)`
      );
      if (!ok) failures++;
    }
  }

  for (const [borderName, min] of BORDER_PAIRS) {
    const panel = token(tokens, '--c-panel', theme);
    const effective = blend(token(tokens, borderName, theme), panel);
    const ratio = contrast(effective, panel);
    const ok = ratio >= min;
    console.log(
      `  ${ok ? 'pass' : 'FAIL'} ${theme} ${borderName} hairline on --c-panel: ${ratio.toFixed(1)}:1 (min ${min}:1)`
    );
    if (!ok) failures++;
  }

  return failures;
}

let totalFailures = 0;
for (const [theme, tokens] of Object.entries(themes)) {
  console.log(`theme: ${theme}`);
  totalFailures += runTheme(theme, tokens);
}

if (totalFailures) {
  console.error(`\n${totalFailures} contrast check(s) failed.`);
  process.exit(1);
}
console.log('\nall contrast checks passed.');
