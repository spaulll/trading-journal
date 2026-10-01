<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { Chart, registerables } from 'chart.js';
	import type { KpiDashboard } from '$lib/api';
	import { fmtMoney, fmtR, pnlTone, toneText } from '$lib/utils/format';
	import { countup } from '$lib/utils/motion';
	import { palette } from '$lib/utils/palette';
	import { theme } from '$lib/stores/theme';

	Chart.register(...registerables);

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
		const p = palette();
		Chart.defaults.color = p.axis;
		Chart.defaults.borderColor = p.grid;
		Chart.defaults.font.family = 'Geist, ui-sans-serif, sans-serif';
		chart?.destroy();
		const pf = kpi.profit_factor ?? 0;
		const filled = Math.min(GAUGE_MAX, Math.max(0, pf));
		chart = new Chart(gauge, {
			type: 'doughnut',
			data: {
				datasets: [
					{
						data: [filled, GAUGE_MAX - filled],
						backgroundColor: [pf >= 1.5 ? p.win : pf >= 1 ? p.flat : p.loss, p.grid],
						borderWidth: 0
					}
				]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				rotation: -90,
				circumference: 180,
				cutout: '82%',
				animation: { duration: 900, easing: 'easeOutQuart' },
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
		void $theme;
		if (gauge) renderGauge();
	});

	onDestroy(() => {
		chart?.destroy();
		chart = null;
	});

	const cells = $derived([
		{
			label: 'Average realized R:R',
			value: fmtR(kpi.avg_realized_rr.current),
			raw: kpi.avg_realized_rr.current,
			format: (v: number) => fmtR(v),
			tone: toneText[pnlTone(kpi.avg_realized_rr.current)]
		},
		{
			label: 'Win rate',
			value: kpi.win_rate.rate,
			raw: kpi.win_rate.rate,
			format: (v: number) => `${v.toFixed(1)}%`,
			tone: 'text-fg'
		},
		{
			label: 'Profit factor',
			value: kpi.profit_factor ?? 0,
			raw: kpi.profit_factor ?? 0,
			format: (v: number) => (kpi.profit_factor === null ? '—' : v.toFixed(2)),
			tone: (kpi.profit_factor ?? 0) >= 1.5 ? 'text-win' : (kpi.profit_factor ?? 0) >= 1 ? 'text-flat' : 'text-loss'
		}
	]);
</script>

<section
	class="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5"
	aria-label="Key performance indicators"
>
	<!-- Hero: net P&L -->
	<div class="card rise relative overflow-hidden p-5 sm:col-span-2 xl:col-span-2">
		<span
			class="pointer-events-none absolute inset-0 {up ? 'kpi-glow-win' : 'kpi-glow-loss'}"
			aria-hidden="true"
		></span>
		<div class="relative flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
			<div class="min-w-0">
				<p class="eyebrow">Net P&amp;L · 30d</p>
				<p
					class="display mt-2 text-[2rem] leading-none wrap-break-word tabular-nums sm:text-[2.4rem] xl:text-[2.6rem] {toneText[tone]} {tone === 'win'
						? 'text-glow-win'
						: tone === 'loss'
							? 'text-glow-loss'
							: ''}"
					use:countup={{ value: kpi.net_pnl, format: (v) => fmtMoney(v) }}
				>
					{fmtMoney(kpi.net_pnl)}
				</p>
			</div>
			<span
				class="shrink-0 rounded-full border border-line bg-raised/70 px-2.5 py-1 font-mono text-[11px] tabular-nums {kpi.net_pnl_change_pct ===
				null
					? 'text-dim'
					: (kpi.net_pnl_change_pct ?? 0) >= 0
						? 'text-win'
						: 'text-loss'}"
			>
				{deltaTxt}
			</span>
		</div>

		{#if spark.length >= 2}
			<svg viewBox="0 0 200 48" class="relative mt-3 h-14 w-full" aria-hidden="true" preserveAspectRatio="none">
				<defs>
					<linearGradient id={sparkId} x1="0" y1="0" x2="0" y2="1">
						<stop offset="0%" stop-color={up ? 'rgb(var(--c-win))' : 'rgb(var(--c-loss))'} stop-opacity="0.38" />
						<stop offset="100%" stop-color={up ? 'rgb(var(--c-win))' : 'rgb(var(--c-loss))'} stop-opacity="0" />
					</linearGradient>
				</defs>
				<polygon points="0,48 {sparkPath} 200,48" fill="url(#{sparkId})" />
				<polyline
					points={sparkPath}
					fill="none"
					stroke={up ? 'rgb(var(--c-win))' : 'rgb(var(--c-loss))'}
					stroke-width="2"
					pathLength="1"
					stroke-linejoin="round"
					stroke-linecap="round"
					style="stroke-dasharray: 1; stroke-dashoffset: 1; animation: draw 1.3s cubic-bezier(0.22, 1, 0.36, 1) 0.25s forwards;"
				/>
			</svg>
		{:else}
			<p class="mt-3 py-4 text-center text-xs text-dim">Not enough data for sparkline.</p>
		{/if}
	</div>

	{#each cells as cell, ci (cell.label)}
		<div class="card rise p-5" style="animation-delay: {(ci + 1) * 80}ms">
			<p class="eyebrow">{cell.label}</p>
			<p
				class="display mt-2 text-[2.1rem] leading-none tabular-nums {cell.tone}"
				use:countup={{ value: cell.raw, format: cell.format }}
			>
				{cell.format(cell.raw)}
			</p>

			{#if cell.label === 'Average realized R:R'}
				<div class="mt-5">
					<div class="relative h-1.5 rounded-full bg-raised">
						<div
							class="absolute top-1/2 h-4 w-1 -translate-y-1/2 rounded-full bg-accent shadow-[0_0_10px_rgb(var(--c-accent)/0.7)]"
							style="left: calc({(rrPos * 100).toFixed(1)}% - 2px)"
							title="Current {fmtR(kpi.avg_realized_rr.current)}"
						></div>
						<div
							class="absolute top-1/2 h-4 w-1 -translate-y-1/2 rounded-full bg-flat/80"
							style="left: calc({(rrTarget * 100).toFixed(1)}% - 2px)"
							title="Target {kpi.avg_realized_rr.target.toFixed(1)}R"
						></div>
					</div>
					<div class="num mt-1.5 flex justify-between text-[10px] text-dim">
						{#each rrMarks as m}
							<span>{m}{m === 5 ? '+' : ''}</span>
						{/each}
					</div>
					<p class="mt-2 text-[11px] text-dim">
						target <span class="num text-mut">{kpi.avg_realized_rr.target.toFixed(1)}R</span>
					</p>
				</div>
			{:else if cell.label === 'Win rate'}
				<div
					class="mt-4 flex items-stretch gap-1.5"
					aria-label="{kpi.win_rate.wins} wins, {kpi.win_rate.losses} losses, {kpi.win_rate.breakeven} breakeven"
				>
					<span class="flex-1 rounded-lg bg-win/12 py-2 text-center font-mono text-sm font-bold text-win tabular-nums" title="Wins">W {kpi.win_rate.wins}</span>
					<span class="flex-1 rounded-lg bg-loss/12 py-2 text-center font-mono text-sm font-bold text-loss tabular-nums" title="Losses">L {kpi.win_rate.losses}</span>
					<span class="flex-1 rounded-lg bg-flat/12 py-2 text-center font-mono text-sm font-bold text-flat tabular-nums" title="Breakeven">BE {kpi.win_rate.breakeven}</span>
				</div>
			{:else}
				<div class="relative mx-auto mt-2 h-24 w-full max-w-52">
					<canvas bind:this={gauge}></canvas>
					<p class="pointer-events-none absolute inset-x-0 bottom-0 text-center text-[11px] tracking-[0.16em] text-dim uppercase">
						scale 0–5
					</p>
				</div>
			{/if}
		</div>
	{/each}
</section>
