<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { Chart, registerables } from 'chart.js';
	import type { RBucket } from '$lib/api';
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
		Chart.defaults.color = p.axis;
		Chart.defaults.borderColor = p.grid;
		Chart.defaults.font.family = 'Geist, ui-sans-serif, sans-serif';
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
				animation: { duration: 800, easing: 'easeOutQuart' },
				plugins: {
					legend: { display: false },
					tooltip: {
						backgroundColor: p.panel,
						titleColor: p.axis,
						bodyColor: p.fg,
						borderColor: p.grid,
						borderWidth: 1,
						padding: 10,
						cornerRadius: 10,
						displayColors: false
					}
				},
				scales: {
					x: {
						grid: { display: false, color: p.grid },
						ticks: { color: p.axis, font: { family: 'Geist Mono', size: 11 } }
					},
					y: {
						beginAtZero: true,
						grid: { color: p.grid },
						ticks: { precision: 0, color: p.axis, font: { family: 'Geist Mono', size: 11 } }
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
		buckets.map((b) => b.count).join(',');
		if (canvas) render();
	});

	onDestroy(() => {
		chart?.destroy();
		chart = null;
	});
</script>

<div class="h-64 w-full"><canvas bind:this={canvas}></canvas></div>
