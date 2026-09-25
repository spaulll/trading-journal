<script lang="ts">
	import { onMount } from 'svelte';
	import uPlot from 'uplot';
	import 'uplot/dist/uPlot.min.css';
	import type { EquityPoint } from '$lib/api';

	const { points }: { points: EquityPoint[] } = $props();

	let wrap: HTMLDivElement | null = null;
	let plot: uPlot | null = null;

	function build(): void {
		if (!wrap || points.length === 0) return;
		plot?.destroy();
		const xs = points.map((p) => new Date(p.timestamp).getTime() / 1000);
		const ys = points.map((p) => p.drawdown);
		const w = wrap.clientWidth || 600;
		plot = new uPlot(
			{
				width: w,
				height: 260,
				cursor: { show: true, x: true, y: true },
				legend: { show: false },
				axes: [
					{
						stroke: '#64748b',
						grid: { stroke: 'rgba(148,163,184,0.12)', width: 1 },
						values: (_u, vals) =>
							vals.map((v) => {
								const d = new Date(v * 1000);
								return `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}`;
							})
					},
					{
						stroke: '#64748b',
						grid: { stroke: 'rgba(148,163,184,0.12)', width: 1 }
					}
				],
				series: [
					{},
					{
						label: 'Drawdown',
						stroke: '#ef4444',
						width: 2,
						fill: (u, _si) => {
							const g = u.ctx.createLinearGradient(0, 0, 0, u.bbox.height);
							g.addColorStop(0, 'rgba(239,68,68,0)');
							g.addColorStop(1, 'rgba(239,68,68,0.35)');
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
		points.length;
		if (wrap) build();
	});
</script>

<div bind:this={wrap} class="h-[260px] w-full"></div>
