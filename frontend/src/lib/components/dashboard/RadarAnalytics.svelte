<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { Chart, registerables } from 'chart.js';
	import type { RadarProfiles } from '$lib/api';
	import { fmtMoney } from '$lib/utils/format';
	import { palette } from '$lib/utils/palette';
	import { theme } from '$lib/stores/theme';

	Chart.register(...registerables);

	const { radar }: { radar: RadarProfiles } = $props();

	const bestDay = $derived.by(() => {
		const ranked = [...radar.weekday].sort((a, b) => b.win_rate - a.win_rate);
		return ranked.find((d) => d.trades > 0) ?? null;
	});
	const worstDay = $derived.by(() => {
		const ranked = [...radar.weekday].sort((a, b) => a.win_rate - b.win_rate);
		return ranked.find((d) => d.trades > 0) ?? null;
	});
	const bestSession = $derived.by(() => {
		const ranked = [...radar.sessions].sort((a, b) => b.net_pnl - a.net_pnl);
		return ranked.find((s) => s.trades > 0) ?? null;
	});

	let dayCanvas: HTMLCanvasElement | null = null;
	let sessCanvas: HTMLCanvasElement | null = null;
	let dayChart: Chart | null = null;
	let sessChart: Chart | null = null;

	function radarOptions(max: number, p: ReturnType<typeof palette>): object {
		return {
			responsive: true,
			maintainAspectRatio: false,
			animation: { duration: 900, easing: 'easeOutQuart' },
			scales: {
				r: {
					min: 0,
					max,
					ticks: { display: false, backdropColor: 'transparent' },
					grid: { color: p.grid },
					angleLines: { color: p.grid },
					pointLabels: {
						color: p.axis,
						font: { family: 'Geist Mono', size: 11 }
					}
				}
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
					displayColors: false
				}
			}
		};
	}

	function render(): void {
		const p = palette();
		Chart.defaults.color = p.axis;
		Chart.defaults.borderColor = p.grid;
		Chart.defaults.font.family = 'Geist, ui-sans-serif, sans-serif';

		if (dayCanvas) {
			dayChart?.destroy();
			dayChart = new Chart(dayCanvas, {
				type: 'radar',
				data: {
					labels: radar.weekday.map((d) => d.day),
					datasets: [
						{
							label: 'Win rate %',
							data: radar.weekday.map((d) => d.win_rate),
							backgroundColor: p.accentSoft,
							borderColor: p.accent,
							pointBackgroundColor: p.accent,
							pointBorderColor: p.panel,
							pointRadius: 3,
							pointHoverRadius: 5,
							borderWidth: 2
						}
					]
				},
				options: radarOptions(100, p)
			});
		}
		if (sessCanvas) {
			sessChart?.destroy();
			const nets = radar.sessions.map((s) => s.net_pnl);
			const shift = Math.min(0, ...nets);
			sessChart = new Chart(sessCanvas, {
				type: 'radar',
				data: {
					labels: radar.sessions.map((s) => s.session.replace('_', ' ').toUpperCase()),
					datasets: [
						{
							label: 'Net PnL (shifted)',
							data: nets.map((n) => n - shift),
							backgroundColor: p.accentSoft,
							borderColor: p.accent,
							pointBackgroundColor: p.accent,
							pointBorderColor: p.panel,
							pointRadius: 3,
							pointHoverRadius: 5,
							borderWidth: 2
						}
					]
				},
				options: radarOptions(Math.max(1, Math.max(...nets.map((n) => n - shift)) * 1.15), p)
			});
		}
	}

	onMount(() => {
		render();
		return () => {
			dayChart?.destroy();
			sessChart?.destroy();
			dayChart = sessChart = null;
		};
	});

	$effect(() => {
		[radar.weekday.map((d) => d.win_rate).join(','), radar.sessions.map((s) => s.net_pnl).join(',')].join('|');
		void $theme;
		if (dayCanvas || sessCanvas) render();
	});

	onDestroy(() => {
		dayChart?.destroy();
		sessChart?.destroy();
		dayChart = sessChart = null;
	});
</script>

<section class="rise grid grid-cols-1 gap-3 md:grid-cols-2" style="animation-delay: 120ms" aria-label="Radar profiles">
	<div class="card p-5">
		<div class="flex items-baseline justify-between gap-3">
			<h3 class="eyebrow">Weekday distribution</h3>
			<span class="eyebrow text-accent">win rate %</span>
		</div>
		{#if bestDay}
			<p class="num mt-1.5 flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-[11.5px] text-dim">
				<span>
					Best: <span class="font-bold text-win">{bestDay.day} ({bestDay.win_rate.toFixed(0)}% WR, {fmtMoney(bestDay.net_pnl)})</span>
				</span>
				{#if worstDay && worstDay.day !== bestDay.day}
					<span>
						· Worst: <span class="font-bold text-loss">{worstDay.day} ({worstDay.win_rate.toFixed(0)}% WR)</span>
					</span>
				{/if}
			</p>
		{/if}
		<div class="mt-2 h-64 min-w-0"><canvas bind:this={dayCanvas}></canvas></div>
	</div>

	<div class="card p-5">
		<div class="flex items-baseline justify-between gap-3">
			<h3 class="eyebrow">Session killzones</h3>
			<span class="eyebrow text-accent">net P&amp;L</span>
		</div>
		{#if bestSession}
			<p class="num mt-1.5 text-[11.5px] text-dim">
				Edge: <span class="font-bold text-win">
					{bestSession.session.replace('_', ' ').toUpperCase()} ({fmtMoney(bestSession.net_pnl)}, {bestSession.win_rate.toFixed(0)}% WR)
				</span>
			</p>
		{/if}
		<div class="mt-2 h-64 min-w-0"><canvas bind:this={sessCanvas}></canvas></div>
	</div>
</section>
