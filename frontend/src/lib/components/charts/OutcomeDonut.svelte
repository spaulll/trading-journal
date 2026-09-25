<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { Chart, registerables } from 'chart.js';
	import type { SummaryDto } from '$lib/api';

	Chart.register(...registerables);
	Chart.defaults.color = '#94a3b8';
	Chart.defaults.borderColor = 'rgba(148,163,184,0.12)';
	Chart.defaults.font.family = 'Inter, sans-serif';

	const { summary }: { summary: SummaryDto } = $props();

	let canvas: HTMLCanvasElement | null = null;
	let chart: Chart | null = null;

	function render(): void {
		if (!canvas) return;
		chart?.destroy();
		chart = new Chart(canvas, {
			type: 'doughnut',
			data: {
				labels: ['Wins', 'Losses', 'Breakeven'],
				datasets: [
					{
						data: [summary.wins, summary.losses, summary.breakeven],
						backgroundColor: ['#10b981', '#ef4444', '#64748b'],
						borderWidth: 0,
						hoverOffset: 6
					}
				]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				cutout: '68%',
				plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, padding: 14 } } }
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
		[summary.wins, summary.losses, summary.breakeven].join(',');
		if (canvas) render();
	});

	onDestroy(() => {
		chart?.destroy();
		chart = null;
	});
</script>

<div class="h-64 w-full"><canvas bind:this={canvas}></canvas></div>
