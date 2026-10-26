#!/usr/bin/env node
// Theme + component contrast audit (see PLAN.MD §1.2, §6.1 and §6.2)
//
// Parses the RGB tokens declared in `frontend/src/app.css` and checks the
// text / hairline / component pairs that must hold in BOTH themes.
//
// Component pairs are checked on the FINAL COMPOSITE SURFACE: a badge is
// `win` ink over `win / 12%` over the panel, so the check paints it in that
// order instead of comparing the two raw tokens. The alpha values below mirror
// the component classes they describe; the browser audit (`npm run audit:ui`)
// measures the same pairs from computed styles.
//
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
  const base = bg.rgb ?? bg;
  return fg.rgb.map((channel, index) => Math.round(alpha * channel + (1 - alpha) * base[index]));
}

// WCAG 2.1: 4.5:1 for normal text, 3:1 for large text and UI boundaries.
const TEXT = 4.5;
const LARGE = 3;
const UI = 3;

const SURFACES = ['--c-panel', '--c-raised', '--c-overlay'];
const TEXT_PAIRS = [
  ['--c-fg', 7],
  ['--c-mut', TEXT],
  ['--c-dim', TEXT],
  ['--c-accent', TEXT],
  ['--c-win', TEXT],
  ['--c-loss', TEXT],
  ['--c-flat', TEXT]
];

/**
 * Text painted over a translucent tint, e.g. the `tag-setup` badge
 * (`--c-win` ink on `--c-win / 0.13` over the panel).
 */
const TINT_PAIRS = [
  { label: 'setup tag', fg: '--c-win', tint: '--c-win', alpha: 0.13, base: '--c-panel' },
  { label: 'mistake tag', fg: '--c-loss', tint: '--c-loss', alpha: 0.13, base: '--c-panel' },
  { label: 'win stat chip', fg: '--c-win', tint: '--c-win', alpha: 0.12, base: '--c-panel' },
  { label: 'loss stat chip', fg: '--c-loss', tint: '--c-loss', alpha: 0.12, base: '--c-panel' },
  { label: 'breakeven stat chip', fg: '--c-flat', tint: '--c-flat', alpha: 0.12, base: '--c-panel' },
  { label: 'calendar win cell', fg: '--c-win', tint: '--c-win', alpha: 0.1, base: '--c-panel' },
  { label: 'calendar loss cell', fg: '--c-loss', tint: '--c-loss', alpha: 0.1, base: '--c-panel' },
  { label: 'calendar breakeven cell', fg: '--c-flat', tint: '--c-flat', alpha: 0.1, base: '--c-panel' }
];

/**
 * Component surfaces that are not a plain token pair: disabled controls,
 * placeholders, tooltips, the danger button gradient, and the focus ring.
 * Each entry names the component so a failure says where to look.
 */
const COMPONENT_PAIRS = [
  { label: 'disabled control label (--c-dim on --c-raised)', fg: '--c-dim', bg: '--c-raised', min: TEXT },
  { label: 'placeholder (--c-dim on --c-raised / 0.7)', fg: '--c-dim', tint: '--c-raised', alpha: 0.7, base: '--c-panel', min: TEXT },
  { label: 'quiet label on base (--c-dim on --c-bg)', fg: '--c-dim', bg: '--c-bg', min: TEXT },
  { label: 'tooltip title (--c-dim on --c-overlay)', fg: '--c-dim', bg: '--c-overlay', min: TEXT },
  { label: 'tooltip body (--c-fg on --c-overlay)', fg: '--c-fg', bg: '--c-overlay', min: TEXT },
  { label: 'active chip label (--c-fg on --c-raised)', fg: '--c-fg', bg: '--c-raised', min: TEXT },
  // The danger button is a gradient; the bottom stop is the lighter end and
  // therefore the worst case for its ink.
  { label: 'danger button ink (top stop)', fg: '--c-brass-ink', tint: '--c-loss', alpha: 1, base: '--c-panel', min: TEXT },
  { label: 'danger button ink (bottom stop)', fg: '--c-brass-ink', tint: '--c-loss', alpha: 0.9, base: '--c-panel', min: TEXT },
  { label: 'primary button ink (top stop)', fg: '--c-brass-ink', tint: '--c-btn-from', alpha: 1, base: '--c-panel', min: TEXT },
  { label: 'primary button ink (bottom stop)', fg: '--c-brass-ink', tint: '--c-btn-to', alpha: 1, base: '--c-panel', min: TEXT }
];

/** Non-text boundaries: focus ring and field focus border need 3:1. */
const UI_PAIRS = [
  { label: 'focus ring on base', fg: '--c-accent', bg: '--c-bg' },
  { label: 'focus ring on panel', fg: '--c-accent', bg: '--c-panel' },
  { label: 'focus ring on raised', fg: '--c-accent', bg: '--c-raised' },
  { label: 'focus ring on overlay', fg: '--c-accent', bg: '--c-overlay' },
  // `.field:focus` paints its border at 90% accent over the field surface.
  {
    label: 'field focus border (--c-accent / 0.9 on --c-raised)',
    fg: '--c-accent',
    alpha: 0.9,
    bg: '--c-raised'
  }
];

// Hairlines are deliberately quiet; this is a visibility floor, not the 3:1
// non-text target. Component-level contrast is covered above.
const BORDER_PAIRS = [
  ['--c-line', 1.15],
  ['--c-edge', 1.15]
];

function token(tokens, name, theme) {
  const value = tokens[name];
  if (!value) throw new Error(`Missing ${name} in the ${theme} theme`);
  return value;
}

function report(label, ratio, min) {
  const ok = ratio >= min;
  console.log(`  ${ok ? 'pass' : 'FAIL'} ${label}: ${ratio.toFixed(2)}:1 (min ${min}:1)`);
  return ok ? 0 : 1;
}

function runTheme(theme, tokens) {
  let failures = 0;

  for (const surfaceName of SURFACES) {
    const surface = token(tokens, surfaceName, theme);
    for (const [textName, min] of TEXT_PAIRS) {
      failures += report(
        `${theme} ${textName} on ${surfaceName}`,
        contrast(token(tokens, textName, theme), surface),
        min
      );
    }
  }

  for (const pair of TINT_PAIRS) {
    const tint = { ...token(tokens, pair.tint, theme), alpha: pair.alpha };
    const surface = blend(tint, token(tokens, pair.base, theme));
    failures += report(
      `${theme} ${pair.label}`,
      contrast(token(tokens, pair.fg, theme), surface),
      TEXT
    );
  }

  for (const pair of COMPONENT_PAIRS) {
    const fg = token(tokens, pair.fg, theme);
    let surface;
    if (pair.tint) {
      surface = blend(
        { ...token(tokens, pair.tint, theme), alpha: pair.alpha },
        token(tokens, pair.base ?? '--c-panel', theme)
      );
    } else {
      surface = token(tokens, pair.bg, theme);
    }
    failures += report(`${theme} ${pair.label}`, contrast(fg, surface), pair.min);
  }

  for (const pair of UI_PAIRS) {
    const surface = token(tokens, pair.bg, theme);
    const fg = token(tokens, pair.fg, theme);
    // Rings and borders are painted over the surface with their own alpha.
    const painted =
      pair.alpha !== undefined
        ? blend({ ...fg, alpha: pair.alpha }, surface)
        : fg.alpha < 1
          ? blend(fg, surface)
          : fg;
    failures += report(`${theme} ${pair.label}`, contrast(painted, surface), UI);
  }

  for (const [borderName, min] of BORDER_PAIRS) {
    const panel = token(tokens, '--c-panel', theme);
    const effective = blend(token(tokens, borderName, theme), panel);
    failures += report(
      `${theme} ${borderName} hairline on --c-panel`,
      contrast(effective, panel),
      min
    );
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
