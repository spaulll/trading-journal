<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { Chart, registerables } from 'chart.js';
	import type { KpiDashboard } from '$lib/api';
	import { fmtMoney, fmtR, pnlTone, toneText } from '$lib/utils/format';

	Chart.register(...registerables);
	Chart.defaults.color = '#94a3b8';
	Chart.defaults.borderColor = 'rgba(148,163,184,0.12)';
	Chart.defaults.font.family = 'Inter, sans-serif';

	const { kpi }: { kpi: KpiDashboard } = $props();

	const tone = $derived(pnlTone(kpi.net_pnl));
	const spark = $derived(kpi.sparkline);
	const sparkPath = $derived.by(() => {
		if (spark.length < 2) return '';
		const w = 200;
		const h = 48;
		const min = Math.min(...spark);
		const max = Math.max(...spark);
		const span = max - min || 1;
		return spark
			.map((v, i) => `${((i / (spark.length - 1)) * w).toFixed(1)},${(h - 4 - ((v - min) / span) * (h - 10)).toFixed(1)}`)
			.join(' ');
	});
	const sparkId = 'kpi-spark-grad';
	const up = $derived(kpi.net_pnl >= 0);

	const deltaTxt = $derived(
		kpi.net_pnl_change_pct === null
			? '— vs prior 30d'
			: `${kpi.net_pnl_change_pct >= 0 ? '▲' : '▼'} ${Math.abs(kpi.net_pnl_change_pct).toFixed(1)}% vs prior 30d`
	);

	// R:R slider positions (0..5 scale).
	const rrPos = $derived(Math.min(5, Math.max(0, kpi.avg_realized_rr.current)) / 5);
	const rrTarget = $derived(Math.min(5, Math.max(0, kpi.avg_realized_rr.target)) / 5);
	const rrMarks = [0, 1, 2, 3, 4, 5];

	let gauge: HTMLCanvasElement | null = null;
	let chart: Chart | null = null;
	const GAUGE_MAX = 5;

	function renderGauge(): void {
		if (!gauge) return;
		chart?.destroy();
		const pf = kpi.profit_factor ?? 0;
		const filled = Math.min(GAUGE_MAX, Math.max(0, pf));
		chart = new Chart(gauge, {
			type: 'doughnut',
			data: {
				datasets: [
					{
						data: [filled, GAUGE_MAX - filled],
						backgroundColor: [pf >= 1.5 ? '#10b981' : pf >= 1 ? '#f59e0b' : '#ef4444', 'rgba(148,163,184,0.15)'],
						borderWidth: 0
					}
				]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				rotation: -90,
				circumference: 180,
				cutout: '80%',
				plugins: { legend: { display: false }, tooltip: { enabled: false } }
			}
		});
	}

	onMount(() => {
		renderGauge();
		return () => {
			chart?.destroy();
			chart = null;
		};
	});

	$effect(() => {
		void kpi.profit_factor;
		if (gauge) renderGauge();
	});

	onDestroy(() => {
		chart?.destroy();
		chart = null;
	});

	const card =
		'rounded-xl border border-slate-200 bg-white p-4 shadow-card dark:border-white/[0.07] dark:bg-surface-900';
</script>

<section class="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="Key performance indicators">
	<div class={card}>
		<p class="text-xs font-medium tracking-wide text-slate-500 dark:text-slate-400">Net P&amp;L</p>
		<div class="mt-1 flex items-baseline justify-between gap-2">
			<p class="font-mono text-2xl font-bold tracking-tight tabular-nums {toneText[tone]}">
				{fmtMoney(kpi.net_pnl)}
			</p>
			<span
				class="rounded-full px-2 py-0.5 font-mono text-[11px] tabular-nums {kpi.net_pnl_change_pct === null
					? 'bg-slate-500/10 text-slate-500 dark:text-slate-400'
					: (kpi.net_pnl_change_pct ?? 0) >= 0
						? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
						: 'bg-rose-500/10 text-rose-600 dark:text-rose-400'}"
			>
				{deltaTxt}
			</span>
		</div>
		{#if spark.length >= 2}
			<svg viewBox="0 0 200 48" class="mt-2 h-12 w-full" aria-hidden="true" preserveAspectRatio="none">
				<defs>
					<linearGradient id={sparkId} x1="0" y1="0" x2="0" y2="1">
						<stop offset="0%" stop-color={up ? '#10b981' : '#ef4444'} stop-opacity="0.35" />
						<stop offset="100%" stop-color={up ? '#10b981' : '#ef4444'} stop-opacity="0" />
					</linearGradient>
				</defs>
				<polygon points="0,48 {sparkPath} 200,48" fill="url(#{sparkId})" />
				<polyline
					points={sparkPath}
					fill="none"
					stroke={up ? '#10b981' : '#ef4444'}
					stroke-width="2"
					stroke-linejoin="round"
					stroke-linecap="round"
					style="filter: drop-shadow(0 0 4px {up ? 'rgba(16,185,129,0.6)' : 'rgba(239,68,68,0.6)'})"
				/>
			</svg>
		{:else}
			<p class="mt-2 py-3 text-center text-xs text-slate-500">Not enough data for sparkline.</p>
		{/if}
	</div>

	<div class={card}>
		<p class="text-xs font-medium tracking-wide text-slate-500 dark:text-slate-400">Average Realized R:R</p>
		<p class="mt-1 font-mono text-2xl font-bold tracking-tight tabular-nums">
			{fmtR(kpi.avg_realized_rr.current)}
			<span class="text-sm font-medium text-slate-500 dark:text-slate-400">/ {kpi.avg_realized_rr.target.toFixed(1)}R target</span>
		</p>
		<div class="mt-4 px-0.5">
			<div class="relative h-1.5 rounded-full bg-slate-200 dark:bg-white/10">
				<div
					class="absolute top-1/2 h-4 w-1 -translate-y-1/2 rounded-full bg-emerald-500 shadow"
					style="left: calc({(rrPos * 100).toFixed(1)}% - 2px)"
					title="Current {fmtR(kpi.avg_realized_rr.current)}"
				></div>
				<div
					class="absolute top-1/2 h-4 w-1 -translate-y-1/2 rounded-full bg-slate-400 dark:bg-slate-500"
					style="left: calc({(rrTarget * 100).toFixed(1)}% - 2px)"
					title="Target {kpi.avg_realized_rr.target.toFixed(1)}R"
				></div>
			</div>
			<div class="mt-1.5 flex justify-between font-mono text-[10px] text-slate-500 tabular-nums dark:text-slate-500">
				{#each rrMarks as m}
					<span>{m}{m === 5 ? '+' : ''}</span>
				{/each}
			</div>
			<div class="mt-1 flex items-center gap-3 text-[11px]">
				<span class="flex items-center gap-1 text-slate-500 dark:text-slate-400">
					<span class="inline-block h-2 w-2 rounded-full bg-emerald-500"></span> Current
				</span>
				<span class="flex items-center gap-1 text-slate-500 dark:text-slate-400">
					<span class="inline-block h-2 w-2 rounded-full bg-slate-400 dark:bg-slate-500"></span> Target
				</span>
			</div>
		</div>
	</div>

	<div class={card}>
		<p class="text-xs font-medium tracking-wide text-slate-500 dark:text-slate-400">Win Rate</p>
		<p class="mt-1 font-mono text-2xl font-bold tracking-tight tabular-nums">
			{kpi.win_rate.rate.toFixed(1)}%
		</p>
		<div class="mt-3 flex items-stretch gap-1.5" aria-label="{kpi.win_rate.wins} wins, {kpi.win_rate.losses} losses, {kpi.win_rate.breakeven} breakeven">
			<span class="flex-1 rounded-lg bg-emerald-500/15 py-2 text-center font-mono text-sm font-bold text-emerald-600 tabular-nums dark:text-emerald-400" title="Wins">W {kpi.win_rate.wins}</span>
			<span class="flex-1 rounded-lg bg-rose-500/15 py-2 text-center font-mono text-sm font-bold text-rose-600 tabular-nums dark:text-rose-400" title="Losses">L {kpi.win_rate.losses}</span>
			<span class="flex-1 rounded-lg bg-slate-500/15 py-2 text-center font-mono text-sm font-bold text-slate-500 tabular-nums dark:text-slate-400" title="Breakeven">BE {kpi.win_rate.breakeven}</span>
		</div>
	</div>

	<div class={card}>
		<p class="text-xs font-medium tracking-wide text-slate-500 dark:text-slate-400">Profit Factor</p>
		<div class="relative mx-auto mt-1 h-28 max-w-56">
			<canvas bind:this={gauge}></canvas>
			<p class="pointer-events-none absolute inset-x-0 bottom-0 text-center font-mono text-2xl font-bold tabular-nums">
				{kpi.profit_factor === null ? '—' : kpi.profit_factor.toFixed(2)}
			</p>
		</div>
	</div>
</section>
