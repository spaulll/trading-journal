<script lang="ts">
	import { onMount } from 'svelte';
	import uPlot from 'uplot';
	import 'uplot/dist/uPlot.min.css';
	import type { EquityPoint } from '$lib/api';
	import { fmtAxisDay, fmtDate, fmtMoney, pnlTone, storedMs } from '$lib/utils/format';
	import { tooltipPlugin } from '$lib/components/charts/uplotTooltip';
	import { palette } from '$lib/utils/palette';
	import { theme } from '$lib/stores/theme';

	const { points }: { points: EquityPoint[] } = $props();

	const AXIS_FONT = '11px "Geist Mono", ui-monospace, monospace';

	/** Rebuild `rgb(r g b)` (with or without alpha) at an explicit alpha. */
	function alpha(color: string, a: number): string {
		const inner = color.startsWith('rgb(') ? color.slice(4, -1) : color;
		return `rgb(${inner.split('/')[0].trim()} / ${a})`;
	}

	let wrap: HTMLDivElement | null = null;
	let plot: uPlot | null = null;

	function build(): void {
		if (!wrap || points.length === 0) return;
		const pal = palette();
		plot?.destroy();
		const xs = points.map((p) => (storedMs(p.timestamp) ?? 0) / 1000);
		const ys = points.map((p) => p.equity);
		const w = wrap.clientWidth || 600;
		// Line color follows the final total net (green/red), flat when |net| <= BE tol.
		const endTone = pnlTone(ys.length ? ys[ys.length - 1] : null);
		const line = endTone === 'win' ? pal.win : endTone === 'loss' ? pal.loss : pal.flat;
		plot = new uPlot(
			{
				width: w,
				height: 260,
				cursor: { show: true, x: true, y: true },
				legend: { show: false },
				plugins: [
					tooltipPlugin((idx) => {
						const p = points[idx];
						if (!p) return null;
						return { title: fmtDate(p.timestamp), value: fmtMoney(p.equity), tone: pnlTone(p.equity) };
					})
				],
				axes: [
					{
						font: AXIS_FONT,
						stroke: pal.axis,
						grid: { stroke: pal.grid, width: 1 },
						values: (_u, vals) => vals.map((v) => fmtAxisDay(v * 1000))
					},
					{
						font: AXIS_FONT,
						stroke: pal.axis,
						grid: { stroke: pal.grid, width: 1 },
						values: (_u, vals) => vals.map((v) => (v >= 1000 || v <= -1000 ? `${(v / 1000).toFixed(1)}k` : `${v}`))
					}
				],
				series: [
					{},
					{
						label: 'Equity',
						stroke: line,
						width: 2,
						fill: (u, _si) => {
							const g = u.ctx.createLinearGradient(0, 0, 0, u.bbox.height);
							g.addColorStop(0, alpha(line, 0.35));
							g.addColorStop(1, alpha(line, 0));
							return g;
						},
						points: { show: false }
					}
				]
			},
			[xs, ys],
			wrap
		);
	}

	onMount(() => {
		build();
		const ro = new ResizeObserver(() => {
			if (wrap && plot) plot.setSize({ width: wrap.clientWidth || 600, height: 260 });
		});
		if (wrap) ro.observe(wrap);
		return () => {
			ro.disconnect();
			plot?.destroy();
			plot = null;
		};
	});

	$effect(() => {
		$theme;
		points.length;
		if (wrap) build();
	});
</script>

<div bind:this={wrap} class="h-[260px] w-full"></div>
