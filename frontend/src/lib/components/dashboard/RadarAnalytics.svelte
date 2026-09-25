<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { Chart, registerables } from 'chart.js';
	import type { RadarProfiles } from '$lib/api';
	import { fmtMoney } from '$lib/utils/format';

	Chart.register(...registerables);
	Chart.defaults.color = '#94a3b8';
	Chart.defaults.borderColor = 'rgba(148,163,184,0.12)';
	Chart.defaults.font.family = 'Inter, sans-serif';

	const { radar }: { radar: RadarProfiles } = $props();

	const gridColor = 'rgba(148,163,184,0.18)';
	const angleColor = '#94a3b8';

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

	function radarOptions(max: number): object {
		return {
			responsive: true,
			maintainAspectRatio: false,
			scales: {
				r: {
					min: 0,
					max,
					ticks: { display: false },
					grid: { color: gridColor },
					angleLines: { color: gridColor },
					pointLabels: { color: angleColor, font: { size: 11 } }
				}
			},
			plugins: { legend: { display: false } }
		};
	}

	function render(): void {
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
							backgroundColor: 'rgba(16,185,129,0.18)',
							borderColor: '#10b981',
							pointBackgroundColor: '#10b981',
							pointRadius: 3,
							borderWidth: 2
						}
					]
				},
				options: radarOptions(100)
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
							backgroundColor: 'rgba(16,185,129,0.18)',
							borderColor: '#10b981',
							pointBackgroundColor: '#10b981',
							pointRadius: 3,
							borderWidth: 2
						}
					]
				},
				options: radarOptions(Math.max(1, Math.max(...nets.map((n) => n - shift)) * 1.15))
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
		if (dayCanvas || sessCanvas) render();
	});

	onDestroy(() => {
		dayChart?.destroy();
		sessChart?.destroy();
		dayChart = sessChart = null;
	});

	const card =
		'rounded-xl border border-slate-200 bg-white p-4 shadow-card dark:border-white/[0.07] dark:bg-surface-900';
	const callout = 'font-mono text-[11px] tabular-nums text-slate-500 dark:text-slate-400';
</script>

<section class="grid grid-cols-1 gap-4 md:grid-cols-2" aria-label="Radar profilers">
	<div class={card}>
		<h3 class="text-[13px] font-semibold tracking-tight">Weekday Distribution</h3>
		{#if bestDay}
			<p class={callout}>
				Best: <span class="font-bold text-emerald-600 dark:text-emerald-400">{bestDay.day} ({bestDay.win_rate.toFixed(0)}% WR, {fmtMoney(bestDay.net_pnl)})</span>
				{#if worstDay && worstDay.day !== bestDay.day}
					· Worst: <span class="font-bold text-rose-600 dark:text-rose-400">{worstDay.day} ({worstDay.win_rate.toFixed(0)}% WR)</span>
				{/if}
			</p>
		{/if}
		<div class="mt-1 h-64"><canvas bind:this={dayCanvas}></canvas></div>
	</div>
	<div class={card}>
		<h3 class="text-[13px] font-semibold tracking-tight">Session Killzones</h3>
		{#if bestSession}
			<p class={callout}>
				Edge: <span class="font-bold text-emerald-600 dark:text-emerald-400">
					{bestSession.session.replace('_', ' ').toUpperCase()} ({fmtMoney(bestSession.net_pnl)}, {bestSession.win_rate.toFixed(0)}% WR)
				</span>
			</p>
		{/if}
		<div class="mt-1 h-64"><canvas bind:this={sessCanvas}></canvas></div>
	</div>
</section>
