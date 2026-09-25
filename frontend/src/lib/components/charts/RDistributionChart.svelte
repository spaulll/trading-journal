<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { Chart, registerables } from 'chart.js';
	import type { RBucket } from '$lib/api';

	Chart.register(...registerables);
	Chart.defaults.color = '#94a3b8';
	Chart.defaults.borderColor = 'rgba(148,163,184,0.12)';
	Chart.defaults.font.family = 'Inter, sans-serif';

	const { buckets }: { buckets: RBucket[] } = $props();

	let canvas: HTMLCanvasElement | null = null;
	let chart: Chart | null = null;

	function colors(): string[] {
		return buckets.map((b) => {
			if (b.label.startsWith('-')) return '#ef4444';
			if (b.label === '0R') return '#64748b';
			return '#10b981';
		});
	}

	function render(): void {
		if (!canvas) return;
		chart?.destroy();
		chart = new Chart(canvas, {
			type: 'bar',
			data: {
				labels: buckets.map((b) => b.label),
				datasets: [
					{
						data: buckets.map((b) => b.count),
						backgroundColor: colors(),
						borderRadius: 6,
						borderSkipped: false
					}
				]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				plugins: { legend: { display: false } },
				scales: {
					x: { grid: { display: false } },
					y: { beginAtZero: true, ticks: { precision: 0 } }
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
		buckets.map((b) => b.count).join(',');
		if (canvas) render();
	});

	onDestroy(() => {
		chart?.destroy();
		chart = null;
	});
</script>

<div class="h-64 w-full"><canvas bind:this={canvas}></canvas></div>
