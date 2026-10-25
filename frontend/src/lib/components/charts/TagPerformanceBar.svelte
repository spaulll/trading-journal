<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { Chart, registerables } from 'chart.js';
	import type { TagPerf } from '$lib/api';
	import {
		applyChartDefaults,
		chartAnimation,
		chartGrid,
		chartTick,
		chartTooltip
	} from '$lib/components/charts/chartTheme';
	import { palette } from '$lib/utils/palette';
	import { BE_TOL, fmtAxisMoney, fmtMoney } from '$lib/utils/format';
	import { drillIntoTag } from '$lib/stores/ledger';
	import { theme } from '$lib/stores/theme';

	Chart.register(...registerables);

	const { tags }: { tags: TagPerf[] } = $props();

	const top = $derived(tags.filter((t) => t.trade_count > 0).slice(0, 10));

	let canvas: HTMLCanvasElement | null = null;
	let chart: Chart | null = null;

	/** Long tags get an ellipsis on the axis; the tooltip keeps the full name. */
	function shortTag(v: string): string {
		return v.length > 15 ? `${v.slice(0, 14)}…` : v;
	}

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
		applyChartDefaults(p);
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
				animation: chartAnimation(),
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
						...chartTooltip(p),
						callbacks: {
							label: (item) => fmtMoney(Number(item.raw)),
							labelTextColor: (item) => {
								const t = list[item.dataIndex];
								return !t
									? p.fg
									: t.net_pnl > BE_TOL
										? p.win
										: t.net_pnl < -BE_TOL
											? p.loss
											: p.flat;
							}
						}
					}
				},
				scales: {
					x: {
						grid: chartGrid(p),
						ticks: { ...chartTick(p), callback: (v) => fmtAxisMoney(Number(v)) }
					},
					y: {
						grid: { display: false },
						ticks: {
							...chartTick(p),
							callback(value) {
								return shortTag(this.getLabelForValue(Number(value)));
							}
						}
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
