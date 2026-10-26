# UI system contract

One sitting read for the trading journal frontend. It settles design
arguments in later cycles: what exists, what is allowed, what is
out of scope, and how to verify a page before calling it done.

This document is the source of truth for Phases 1–6. The plan owns the
commit list; this file owns the rules the commits implement.

## 1. Stack and scope

- SvelteKit + Tailwind, adapter-node build. Node 20 LTS.
- App routes under `/api` are owned by the backend. This document only
  describes the browser-facing UI contract.
- Design is a dense fintech dashboard. Pages lead with data, not with
  hero copy. The frame is quiet; the numbers are loud.
- The wordmark and page titles use Instrument Serif. Everything else
  uses Geist. Numbers, labels, dates, and table headers use Geist Mono.
- No new fonts. The three self-hosted families are the complete type
  system.
- No animation library. No component library. No Google Fonts. No CDN
  dependencies for the visual system.

## 2. Surfaces

Four roles plus a hairline. Depth comes from surface steps and a subtle
inset top highlight, not from a large drop shadow.

| Role | Dark | Light | Use |
|---|---|---|---|
| `base` | warm ink | warm paper | page canvas |
| `panel` | one step lighter than base | white | primary cards |
| `raised` | two steps lighter | paper tint | inputs, active nav, nested controls |
| `overlay` | lifted charcoal | white with edge | dialogs, menus, tooltips |

Border roles:

| Token | Use |
|---|---|
| `line` | standard hairline |
| `edge` | stronger border for focus and selected states |

Brass stays rare. One brass action per viewport is the practical ceiling.
Active navigation may use brass for its marker and icon, not as a full
gold fill.

## 3. Type

Fluid scale, `clamp()` with rem bounds. Functional text never shrinks
below 11px on phones; display text never exceeds its desktop cap.

| Name | Use | Approx range |
|---|---|---|
| `2xs` | overline / table labels | 10–11px |
| `xs` | metadata, helper text | 11–12px |
| `sm` | controls, tags, table body | 12–13.5px |
| `base` | body copy | 14–15.5px |
| `lg` | card titles | 16–18px |
| `xl` | section headings | 20–22px |
| `2xl` | page headings | 24–28px |
| `display` | page masthead | 36–56px |

Type rules:

- Instrument Serif: wordmark and page titles at 28px and above only.
- Geist: all UI headings below 28px, including modal and state-block titles.
- Geist Mono: labels, numbers, dates, table headers, and status text.
- `font-variant-numeric: tabular-nums` on every numeric surface.
- `text-wrap: balance` on headings, `pretty` on body copy.
- Line height: 1.05–1.15 for display, 1.45–1.6 for body, 1.25 for dense rows.

Default card radius is 14px. Controls are 10px. Pills are full. No new
`rounded-3xl` cards. Borders are 1px hairlines.

## 4. Color and contrast

Contrast is checked on the final composite surface, not on the raw token
color in isolation.

Minimums on the panel surface:

| Token | Use | Minimum |
|---|---|---|
| `fg` | primary text | 12:1 |
| `mut` | secondary body text | 6.5:1 |
| `dim` | 10–11px mono labels | 4.5:1; raise size if needed |
| `accent` | active text and focus | 4.5:1 |
| `win` / `loss` | semantic values | 4.5:1 |
| focus ring | keyboard state | 3:1 against adjacent surface |

Disabled controls remain readable. Opacity alone is not a disabled state.
Placeholder text, chart labels, tooltip text, badge text, and low-value
calendar cells are all contrast-checked on their real surface.

Do not use brass for success, danger, chart series, or every icon. One
accent has power only when it is rare.

## 5. Motion

One motion language. Motion explains where a thing came from and where it
went; it never makes the user wait.

| Token | Duration | Use |
|---|---|---|
| `fast` | 140ms | hover, icon, color |
| `base` | 220ms | rows, tabs |
| `slow` | 320ms | drawers, large panels |
| `spring` | cubic-bezier(0.22, 1, 0.36, 1) | entrances |
| `soft` | cubic-bezier(0.4, 0, 0.2, 1) | exits and fades |

Rules:

- Animate `transform` and `opacity` only. No layout properties.
- No animated numbers, no fake loading delays, no scroll hijacking.
- Cap stagger at 8 items. Total delay under 280ms.
- Every transition has a reduced-motion branch.
- If a motion does not explain a state change, remove it.
- Route changes: short fade plus 4px rise. No full-screen blur or long slide.
- Dialogs and drawers: shared backdrop/panel timing. No bounce.
- Tables: hover/focus on a 200ms background/border transition. No row lift.
- Charts: opacity/clip reveal on first mount. Data updates are instant.

Reduced motion: opacity-only, 120ms maximum, or instant for large
movements. All content stays visible.

## 6. Layout and pages

- Desktop min-height is `100dvh`, never `100vh`.
- Single-line desktop nav is 80px or less.
- Every section has an explicit `<768px` single-column fallback.
- Dense pages keep the data near the fold. Section spacing is 24–32px,
  not 64px.
- Tables: 36–40px rows, 1px row rules, right-aligned numbers, no zebra
  stripes unless contrast testing proves they help.
- Headers: sticky within the table scroll container, 10–11px mono,
  uppercase, letter-spaced, one hairline below.
- Forms: label above control, 4px label gap, 36–40px controls, errors
  inline under the field, sticky footer with one primary action.
- Empty states are starter actions: one primary action, optional quick
  choices, a short explanation. No 400px decorative placeholder.
- Container-query typography for dense cards and tables, so text responds
  to its actual column width rather than only the viewport.

Page patterns:

- Dashboard: one lead metric, supporting context, no four-equal-card row.
- Ledger: one shared grid template for header and rows, so columns align
  by construction.
- Drawer: scrollable body that never hides the primary action.
- Journal: day panel, notes, tag input, and calendar cells share the
  surface/type system.
- Prop: net is the lead number. Spent/received support it. ROI is a
  compact ratio with a one-line explanation, not a fourth hero card.

## 7. Focus and keyboard

One keyboard language.

- Global ring: 2px brass outline, outside the box, 2px gap.
- Inside overflow-hidden surfaces: `.focus-inset` paints the same ring on
  the inside edge.
- Table rows own their focus state, not only a hover tint.
- Form fields paint a full-strength border plus halo; `outline-none`
  removes only the global ring.
- Chip and segmented-control buttons are real buttons with a visible focus
  state; the pill is decorative, not interactive.
- Calendar tiles are focusable, with the same brass outline as the rest of
  the app.
- Skip link is first in tab order.
- Dialog layers trap Tab and restore focus to the trigger on close.
- Escape closes the topmost layer only.

Icons are decorative SVG with `aria-hidden`. They never become tab stops.
Lucide Svelte icons in this project do not emit `tabindex` or
`focusable` by default, so they do not need per-instance suppression.

## 8. Touch, resize, and escape hatches

- Resize separators are focusable, report `aria-valuenow`, min, max, and
  text, and respond to arrows and Home.
- Autosave status is `role="status"` with polite, atomic announcements.
- Search inputs have explicit `aria-label`s.
- Ledger rows and trade cards activate on Enter and Space.
- The `/` shortcut must not steal focus while a dialog is open.

## 9. Theme and fonts

- Two themes only: dark and light. No user-selectable themes beyond these.
- Dark default. Theme is stored in localStorage under `tj-theme`.
- Fonts are self-hosted and preloaded. `font-display: swap`.
- Fallback metrics are tuned so the page does not jump when Geist or
  Instrument Serif loads.
- No layout shift when fonts swap in. No flash of unstyled text from
  external providers. There are none.

## 10. Do not add

- Page layouts, component structure, route order, and information
  architecture changes belong in a planned phase, not in a contrast pass.
- New fonts, colors beyond the token roles, and decorative gradient work.
- An animation library or a component library.
- Data pages as hero sections, bento galleries, or marquees.
- Brass for success, danger, chart series, or every icon.
- Animated numbers, fake loading delays, or scroll hijacking.
- Layout animation (`width`, `height`, `top`, `left`).
- Sticky shell bars that cover table rows after scrolling.
- Hiding information to make a layout breathe. Fix the hierarchy instead.

## 11. Verification

Before calling a page done, answer these out loud:

1. What is the one metric or action the eye should land on first?
2. Is there a second accent competing with it?
3. Are there more card boundaries than information boundaries?
4. Does the densest row still read at 375px?
5. Does the page work in light mode and with reduced motion?
6. Does keyboard focus land somewhere visible on every control?
7. Is anything clipped, overlapping, or hidden behind the shell?
8. Would removing one decoration make the page better? If yes, remove it.

Commands:

- `npm run check` — typecheck.
- `npm run build` — production bundle.
- `npm run check:contrast` — token and composite contrast audit.
- `npm run audit:ui -- --base-url <url>` — repeatable Playwright audit for
  core routes, both themes, reduced motion, and required viewports.

The audit checks `/`, `/analytics`, `/accounts`, `/prop`, `/journal`, and
`/tags` at 375×667 and 1280×800, plus 768×1024 for tables. It fails on
horizontal overflow, collapsed containers, and missing focus indicators,
not just on screenshots.

The backend suite still has to pass after any frontend change. No trade,
account, FX, or cash math gets touched by these rules.
