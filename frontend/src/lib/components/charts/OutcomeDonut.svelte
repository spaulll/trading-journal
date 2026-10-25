<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { Chart, registerables } from 'chart.js';
	import type { SummaryDto } from '$lib/api';
	import {
		applyChartDefaults,
		chartAnimation,
		chartTooltip,
		CHART_MONO
	} from '$lib/components/charts/chartTheme';
	import { palette } from '$lib/utils/palette';
	import { theme } from '$lib/stores/theme';

	Chart.register(...registerables);

	const { summary }: { summary: SummaryDto } = $props();

	let canvas: HTMLCanvasElement | null = null;
	let chart: Chart | null = null;

	// BE matches backend BE_TOLERANCE (|net| <= 5). The BE slice + legend
	// always render — a zero BE is a flat 0° arc, hidden only when total === 0.
	const total = $derived(summary.wins + summary.losses + summary.breakeven);

	function render(): void {
		if (!canvas) return;
		const p = palette();
		applyChartDefaults(p);
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
				animation: chartAnimation(),
				plugins: {
					legend: {
						position: 'bottom',
						labels: {
							color: p.axis,
							font: { family: CHART_MONO, size: 11 },
							usePointStyle: true,
							pointStyle: 'circle',
							boxWidth: 8,
							padding: 12
						}
					},
					tooltip: {
						...chartTooltip(p),
						callbacks: {
							labelTextColor: (item) =>
								[p.win, p.loss, p.flat][item.dataIndex] ?? p.fg
						}
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
