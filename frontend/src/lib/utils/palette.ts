/**
 * Reads the live theme tokens from CSS custom properties so canvas charts
 * (Chart.js / uPlot) follow the dark ⇄ light swap instead of hardcoding hex.
 * Values are stored as `R G B` triplets, optionally with a fixed alpha.
 */
export function cssVar(name: string): string {
	if (typeof document === 'undefined') return 'rgb(128 128 128)';
	const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
	return raw ? `rgb(${raw})` : 'rgb(128 128 128)';
}

/** Same token, forced to an explicit alpha (drops any baked-in alpha). */
export function cssVarA(name: string, alpha: number): string {
	if (typeof document === 'undefined') return `rgb(128 128 128 / ${alpha})`;
	const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
	const base = raw.split('/')[0].trim();
	return `rgb(${base} / ${alpha})`;
}

export interface Palette {
	win: string;
	winSoft: string;
	loss: string;
	lossSoft: string;
	flat: string;
	accent: string;
	accentSoft: string;
	axis: string;
	grid: string;
	panel: string;
	fg: string;
}

/** Snapshot of every token a chart needs. Call right before rendering. */
export function palette(): Palette {
	return {
		win: cssVar('--c-win'),
		winSoft: cssVarA('--c-win', 0.18),
		loss: cssVar('--c-loss'),
		lossSoft: cssVarA('--c-loss', 0.18),
		flat: cssVar('--c-flat'),
		accent: cssVar('--c-accent'),
		accentSoft: cssVarA('--c-accent', 0.18),
		axis: cssVar('--c-dim'),
		grid: cssVar('--c-line'),
		panel: cssVar('--c-panel'),
		fg: cssVar('--c-fg')
	};
}
