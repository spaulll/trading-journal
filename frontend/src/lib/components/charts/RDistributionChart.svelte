<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { Chart, registerables } from 'chart.js';
	import type { RBucket } from '$lib/api';
	import {
		applyChartDefaults,
		chartAnimation,
		chartGrid,
		chartTick,
		chartTooltip
	} from '$lib/components/charts/chartTheme';
	import { palette } from '$lib/utils/palette';
	import { theme } from '$lib/stores/theme';

	Chart.register(...registerables);

	const { buckets }: { buckets: RBucket[] } = $props();

	let canvas: HTMLCanvasElement | null = null;
	let chart: Chart | null = null;

	function colors(p: ReturnType<typeof palette>): string[] {
		return buckets.map((b) => {
			if (b.label.startsWith('-')) return p.loss;
			if (b.label === '0R') return p.flat;
			return p.win;
		});
	}

	function render(): void {
		if (!canvas) return;
		const p = palette();
		applyChartDefaults(p);
		chart?.destroy();
		chart = new Chart(canvas, {
			type: 'bar',
			data: {
				labels: buckets.map((b) => b.label),
				datasets: [
					{
						data: buckets.map((b) => b.count),
						backgroundColor: colors(p),
						borderRadius: 6,
						borderSkipped: false
					}
				]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				animation: chartAnimation(),
				plugins: {
					legend: { display: false },
					tooltip: {
						...chartTooltip(p),
						callbacks: {
							label: (item) => `${item.raw} trade${Number(item.raw) === 1 ? '' : 's'}`,
							labelTextColor: (item) => colors(p)[item.dataIndex] ?? p.fg
						}
					}
				},
				scales: {
					x: {
						grid: { display: false },
						ticks: chartTick(p)
					},
					y: {
						beginAtZero: true,
						grid: chartGrid(p),
						ticks: { ...chartTick(p), precision: 0 }
					}
				}
			}
		});
	}

	onMount(() => {
		render();
		return () => {
			chart?.destroy();
			chart = null;
		};
	});

	$effect(() => {
		$theme;
		buckets;
		if (canvas) render();
	});

	onDestroy(() => {
		chart?.destroy();
		chart = null;
	});
</script>

<div class="h-64 w-full"><canvas bind:this={canvas}></canvas></div>
