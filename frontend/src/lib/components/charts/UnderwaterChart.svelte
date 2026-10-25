<script lang="ts">
	import { onMount } from 'svelte';
	import uPlot from 'uplot';
	import 'uplot/dist/uPlot.min.css';
	import type { EquityPoint } from '$lib/api';
	import { fmtDate, fmtDateTime, fmtMoney, pnlTone, storedMs } from '$lib/utils/format';
	import {
		alpha,
		moneyAxisValues,
		timeAxisValues,
		uplotAxes
	} from '$lib/components/charts/chartTheme';
	import { tooltipPlugin } from '$lib/components/charts/uplotTooltip';
	import { palette } from '$lib/utils/palette';
	import { theme } from '$lib/stores/theme';

	const { points }: { points: EquityPoint[] } = $props();

	let wrap: HTMLDivElement | null = null;
	let plot: uPlot | null = null;

	function build(): void {
		if (!wrap || points.length === 0) return;
		const pal = palette();
		plot?.destroy();
		const xs = points.map((p) => (storedMs(p.timestamp) ?? 0) / 1000);
		const ys = points.map((p) => p.drawdown);
		const w = wrap.clientWidth || 600;
		const span = xs.length > 1 ? xs[xs.length - 1] - xs[0] : 0;
		const intraday = xs.length > 0 && span < 24 * 60 * 60;
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
						return {
							title: intraday ? fmtDateTime(p.timestamp) : fmtDate(p.timestamp),
							value: fmtMoney(p.drawdown),
							tone: pnlTone(p.drawdown)
						};
					})
				],
				axes: uplotAxes(pal, timeAxisValues(intraday), moneyAxisValues()),
				series: [
					{},
					{
						label: 'Drawdown',
						stroke: pal.loss,
						width: 2,
						fill: (u, _si) => {
							const g = u.ctx.createLinearGradient(0, 0, 0, u.bbox.height);
							g.addColorStop(0, alpha(pal.loss, 0));
							g.addColorStop(1, alpha(pal.loss, 0.35));
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
		points;
		if (wrap) build();
	});
</script>

<div bind:this={wrap} class="h-[260px] w-full"></div>
