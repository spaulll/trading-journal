// Shared motion constants (see PLAN.MD §2.2 — motion contract).
//
// These durations and easing curves are the single source of truth for every
// Svelte transition, CSS transition, and stagger in the app.  Nothing here
// creates new dependencies; everything resolves through `svelte/transition`
// and the Tailwind `transitionTimingFunction` tokens (`spring`, `soft`).

export const MOTION = {
	fast: { ms: 140, ease: 'ease' },
	base: { ms: 220, ease: 'ease' },
	slow: { ms: 320, ease: 'ease' },
	dialog: { ms: 260, ease: 'spring' },
	drawer: { ms: 280, ease: 'spring' },
	drop: { ms: 200, ease: 'soft' },
	route: { ms: 180, ease: 'soft' },
} as const;

export const STAGGER_MAX = 8;
export const STAGGER_DELAY = 32; // ms between items, capped at STAGGER_MAX
