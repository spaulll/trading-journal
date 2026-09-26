<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { Chart, registerables } from 'chart.js';
	import type { SummaryDto } from '$lib/api';
	import { palette } from '$lib/utils/palette';
	import { theme } from '$lib/stores/theme';

	Chart.register(...registerables);

	const { summary }: { summary: SummaryDto } = $props();

	let canvas: HTMLCanvasElement | null = null;
	let chart: Chart | null = null;

	// BE matches backend BE_TOLERANCE (|net| <= 0.01). The BE slice + legend
	// always render — a zero BE is a flat 0° arc, hidden only when total === 0.
	const total = $derived(summary.wins + summary.losses + summary.breakeven);

	function render(): void {
		if (!canvas) return;
		const p = palette();
		Chart.defaults.color = p.axis;
		Chart.defaults.borderColor = p.grid;
		Chart.defaults.font.family = 'Geist, ui-sans-serif, sans-serif';
		chart?.destroy();
		chart = new Chart(canvas, {
			type: 'doughnut',
			data: {
				labels: ['Wins', 'Losses', 'Breakeven'],
				datasets: [
					{
						data: [summary.wins, summary.losses, summary.breakeven],
						backgroundColor: [p.win, p.loss, p.flat],
						borderColor: p.panel,
						borderWidth: 3,
						hoverOffset: 6
					}
				]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				cutout: '70%',
				animation: { duration: 800, easing: 'easeOutQuart', animateRotate: true },
				plugins: {
					legend: {
						position: 'bottom',
						labels: {
							color: p.axis,
							font: { family: 'Geist', size: 11 },
							usePointStyle: true,
							pointStyle: 'circle',
							boxWidth: 8,
							padding: 12
						}
					},
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
		[summary.wins, summary.losses, summary.breakeven].join(',');
		if (canvas) render();
	});

	onDestroy(() => {
		chart?.destroy();
		chart = null;
	});
</script>

<div class="h-64 w-full">
	{#if total === 0}
		<p class="py-10 text-center text-sm text-mut">No closed trades yet.</p>
	{:else}
		<canvas bind:this={canvas}></canvas>
	{/if}
</div>
