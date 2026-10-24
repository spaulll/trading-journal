// Shared motion timing tokens (see PLAN.MD §2.2 — motion contract).
//
// Durations and easing curves used by Svelte transitions and CSS. This is the
// single source of truth; nothing here creates new dependencies.

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
export const STAGGER_DELAY = 32;
