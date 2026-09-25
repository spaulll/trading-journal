<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { Chart, registerables } from 'chart.js';
	import type { TagPerf } from '$lib/api';

	Chart.register(...registerables);
	Chart.defaults.color = '#94a3b8';
	Chart.defaults.borderColor = 'rgba(148,163,184,0.12)';
	Chart.defaults.font.family = 'Inter, sans-serif';

	const { tags }: { tags: TagPerf[] } = $props();

	const top = $derived(tags.filter((t) => t.trade_count > 0).slice(0, 10));

	let canvas: HTMLCanvasElement | null = null;
	let chart: Chart | null = null;

	function render(list: TagPerf[]): void {
		if (!canvas) return;
		chart?.destroy();
		chart = new Chart(canvas, {
			type: 'bar',
			data: {
				labels: list.map((t) => `${t.category === 'mistake' ? '!' : '#'}${t.name}`),
				datasets: [
					{
						data: list.map((t) => t.net_pnl),
						backgroundColor: list.map((t) => (t.net_pnl >= 0 ? '#10b981' : '#ef4444')),
						borderRadius: 6,
						borderSkipped: false
					}
				]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				indexAxis: 'y',
				plugins: { legend: { display: false } },
				scales: {
					x: { ticks: { callback: (v) => `$${v}` } },
					y: { grid: { display: false }, ticks: { font: { size: 11 } } }
				}
			}
		});
	}

	onMount(() => {
		render(top);
		return () => {
			chart?.destroy();
			chart = null;
		};
	});

	$effect(() => {
		render(top);
	});

	onDestroy(() => {
		chart?.destroy();
		chart = null;
	});
</script>

<div class="h-64 w-full"><canvas bind:this={canvas}></canvas></div>
