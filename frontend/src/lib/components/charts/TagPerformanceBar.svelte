<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { Chart, registerables } from 'chart.js';
	import type { TagPerf } from '$lib/api';
	import { palette } from '$lib/utils/palette';
	import { theme } from '$lib/stores/theme';

	Chart.register(...registerables);

	const { tags }: { tags: TagPerf[] } = $props();

	const top = $derived(tags.filter((t) => t.trade_count > 0).slice(0, 10));

	let canvas: HTMLCanvasElement | null = null;
	let chart: Chart | null = null;

	function render(list: TagPerf[]): void {
		if (!canvas) return;
		const p = palette();
		Chart.defaults.color = p.axis;
		Chart.defaults.borderColor = p.grid;
		Chart.defaults.font.family = 'Geist, ui-sans-serif, sans-serif';
		chart?.destroy();
		chart = new Chart(canvas, {
			type: 'bar',
			data: {
				labels: list.map((t) => `${t.category === 'mistake' ? '!' : '#'}${t.name}`),
				datasets: [
					{
						data: list.map((t) => t.net_pnl),
						backgroundColor: list.map((t) => (t.net_pnl >= 0 ? p.win : p.loss)),
						borderRadius: 6,
						borderSkipped: false
					}
				]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				indexAxis: 'y',
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
						grid: { color: p.grid },
						ticks: { callback: (v) => `$${v}`, color: p.axis, font: { family: 'Geist Mono', size: 11 } }
					},
					y: {
						grid: { display: false, color: p.grid },
						ticks: { color: p.axis, font: { family: 'Geist Mono', size: 11 } }
					}
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
		$theme;
		render(top);
	});

	onDestroy(() => {
		chart?.destroy();
		chart = null;
	});
</script>

<div class="h-64 w-full"><canvas bind:this={canvas}></canvas></div>
