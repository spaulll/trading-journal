import { Chart } from 'chart.js';
import type uPlot from 'uplot';
import type { Palette } from '$lib/utils/palette';
import { fmtAxisDay, fmtAxisMoney, fmtAxisTime } from '$lib/utils/format';
import { prefersReducedMotion } from '$lib/utils/motion';

/**
 * One chrome for every chart: Geist Mono labels, one grid/axis palette, and a
 * single overlay tooltip language. Canvas charts cannot read Tailwind classes,
 * so the values below mirror the CSS tokens.
 */
export const CHART_MONO = 'Geist Mono, ui-monospace, monospace';
export const UPLOT_AXIS_FONT = '11px "Geist Mono", ui-monospace, monospace';

const AXIS_SIZE = 11;
const TOOLTIP_TITLE_SIZE = 10;
const TOOLTIP_BODY_SIZE = 12;
const TOOLTIP_RADIUS = 10;
const TOOLTIP_PADDING = 8;

const CHART_ANIMATION = { duration: 800, easing: 'easeOutQuart' } as const;

/** Shared Chart.js defaults; call right before a chart is created. */
export function applyChartDefaults(p: Palette): void {
	Chart.defaults.color = p.axis;
	Chart.defaults.borderColor = p.grid;
	Chart.defaults.font.family = CHART_MONO;
	Chart.defaults.font.size = AXIS_SIZE;
}

/** Overlay surface + mono type + hairline edge, matching the uPlot tooltip. */
export function chartTooltip(p: Palette) {
	return {
		backgroundColor: p.overlay,
		titleColor: p.axis,
		bodyColor: p.fg,
		borderColor: p.edge,
		borderWidth: 1,
		padding: TOOLTIP_PADDING,
		cornerRadius: TOOLTIP_RADIUS,
		displayColors: false,
		caretSize: 0,
		caretPadding: 8,
		titleFont: { family: CHART_MONO, size: TOOLTIP_TITLE_SIZE, weight: 500 },
		bodyFont: { family: CHART_MONO, size: TOOLTIP_BODY_SIZE, weight: 600 },
		titleMarginBottom: 4
	};
}

/** Axis labels: dim, 11px mono. Spread into a scale's `ticks`. */
export function chartTick(p: Palette) {
	return { color: p.axis, font: { family: CHART_MONO, size: AXIS_SIZE } };
}

/** Grid line: the same hairline as the card borders. */
export function chartGrid(p: Palette) {
	return { color: p.grid };
}

/** Charts appear at their final state when the OS asks for reduced motion. */
export function chartAnimation(): false | typeof CHART_ANIMATION {
	return prefersReducedMotion() ? false : CHART_ANIMATION;
}

/** Rebuild `rgb(r g b)` (with or without alpha) at an explicit alpha. */
export function alpha(color: string, a: number): string {
	const inner = color.startsWith('rgb(') ? color.slice(4, -1) : color;
	return `rgb(${inner.split('/')[0].trim()} / ${a})`;
}

type AxisValues = (u: uPlot, splits: number[]) => string[];

/**
 * uPlot can split a time scale finer than the label resolution (e.g. 30s
 * ticks formatted as HH:mm). Blank repeated labels so the axis never draws
 * the same minute twice.
 */
export function timeAxisValues(intraday: boolean): AxisValues {
	return (_u, vals) => {
		let last = '';
		return vals.map((v) => {
			const label = intraday ? fmtAxisTime(v * 1000) : fmtAxisDay(v * 1000);
			if (label === last) return '';
			last = label;
			return label;
		});
	};
}

export function moneyAxisValues(): AxisValues {
	return (_u, vals) => vals.map(fmtAxisMoney);
}

/** uPlot axes: same font, stroke, and grid on both charts. */
export function uplotAxes(p: Palette, xValues: AxisValues, yValues: AxisValues): uPlot.Axis[] {
	const base = (values: AxisValues, space: number): uPlot.Axis => ({
		font: UPLOT_AXIS_FONT,
		stroke: p.axis,
		grid: { stroke: p.grid, width: 1 },
		space,
		values
	});
	// HH:mm labels are ~33px wide; 40px of tick space keeps them from touching
	// at 375 without falling back to a single tick.
	return [base(xValues, 40), base(yValues, 30)];
}
