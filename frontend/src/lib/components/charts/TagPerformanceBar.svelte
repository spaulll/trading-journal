<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { Chart, registerables } from 'chart.js';
	import type { TagPerf } from '$lib/api';
	import { palette } from '$lib/utils/palette';
	import { BE_TOL } from '$lib/utils/format';
	import { drillIntoTag } from '$lib/stores/ledger';
	import { theme } from '$lib/stores/theme';

	Chart.register(...registerables);

	const { tags }: { tags: TagPerf[] } = $props();

	const top = $derived(tags.filter((t) => t.trade_count > 0).slice(0, 10));

	let canvas: HTMLCanvasElement | null = null;
	let chart: Chart | null = null;

	/** Clicking a bar opens the ledger on that tag — the trades behind it. */
	function drill(index: number): void {
		const tag = top[index];
		if (!tag) return;
		drillIntoTag(tag.name);
		void goto('/');
	}

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
						backgroundColor: list.map((t) =>
							t.net_pnl > BE_TOL ? p.win : t.net_pnl < -BE_TOL ? p.loss : p.flat
						),
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
				onClick: (_event, elements) => {
					if (elements.length > 0) drill(elements[0].index);
				},
				onHover: (event, elements) => {
					if (!canvas) return;
					canvas.style.cursor = elements.length > 0 ? 'pointer' : 'default';
				},
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
						displayColors: false,
						callbacks: {
							afterLabel: () => 'click to see the trades'
						}
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
<p class="mt-2 text-[11px] text-dim">Click a bar to open the ledger on that tag.</p>
