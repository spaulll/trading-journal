<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { Chart, registerables } from 'chart.js';
	import type { ActivityStreaks, DirectionStats } from '$lib/api';
	import { fmtMoney } from '$lib/utils/format';

	Chart.register(...registerables);
	Chart.defaults.color = '#94a3b8';
	Chart.defaults.borderColor = 'rgba(148,163,184,0.12)';
	Chart.defaults.font.family = 'Inter, sans-serif';

	const {
		longShort,
		activity
	}: {
		longShort: { buy: DirectionStats; sell: DirectionStats };
		activity: ActivityStreaks;
	} = $props();

	let side = $state<'all' | 'long' | 'short'>('all');

	const sel = $derived.by((): DirectionStats => {
		if (side === 'long') return longShort.buy;
		if (side === 'short') return longShort.sell;
		const b = longShort.buy;
		const s = longShort.sell;
		const wins = b.wins + s.wins;
		const losses = b.losses + s.losses;
		const be = b.breakeven + s.breakeven;
		const total = wins + losses + be;
		const best =
			(b.best?.net_pnl ?? -Infinity) >= (s.best?.net_pnl ?? -Infinity) ? b.best : s.best;
		const worst =
			(b.worst?.net_pnl ?? Infinity) <= (s.worst?.net_pnl ?? Infinity) ? b.worst : s.worst;
		return {
			trades: b.trades + s.trades,
			wins,
			losses,
			breakeven: be,
			win_rate: total ? (wins / total) * 100 : 0,
			avg_win: wins ? (b.avg_win * b.wins + s.avg_win * s.wins) / wins : 0,
			avg_loss: losses ? (b.avg_loss * b.losses + s.avg_loss * s.losses) / losses : 0,
			best,
			worst,
			avg_win_duration_min: null,
			avg_loss_duration_min: null,
			max_win_streak: Math.max(b.max_win_streak, s.max_win_streak)
		};
	});

	function fmtDur(min: number | null): string {
		if (min === null) return '—';
		if (min < 60) return `${Math.round(min)}m`;
		const h = Math.floor(min / 60);
		const m = Math.round(min % 60);
		return m ? `${h}h ${m}m` : `${h}h`;
	}

	const winRows = $derived([
		{ label: 'Total Winners', value: `${sel.wins}` },
		{ label: 'Best Win', value: sel.best ? `${sel.best.ticket} · ${fmtMoney(sel.best.net_pnl)}` : '—' },
		{ label: 'Average Win', value: fmtMoney(sel.avg_win) },
		{ label: 'Avg Win Duration', value: fmtDur(sel.avg_win_duration_min) },
		{ label: 'Max Win Streak', value: `${sel.max_win_streak}` }
	]);
	const lossRows = $derived([
		{ label: 'Total Losers', value: `${sel.losses}` },
		{ label: 'Worst Loss', value: sel.worst ? `${sel.worst.ticket} · ${fmtMoney(sel.worst.net_pnl)}` : '—' },
		{ label: 'Average Loss', value: fmtMoney(sel.avg_loss) },
		{ label: 'Avg Loss Duration', value: fmtDur(sel.avg_loss_duration_min) },
		{ label: 'Max Loss Streak', value: `${activity.max_loss_streak}` }
	]);

	const overview = $derived([
		{ label: 'Average Win', value: fmtMoney(sel.avg_win), tone: 'text-accent-win' },
		{ label: 'Average Loss', value: fmtMoney(sel.avg_loss), tone: 'text-accent-loss' },
		{
			label: 'Best Trade',
			value: activity.best_trade ? `${activity.best_trade.ticket} · ${fmtMoney(activity.best_trade.net_pnl)}` : '—',
			tone: 'text-accent-win'
		},
		{
			label: 'Worst Trade',
			value: activity.worst_trade ? `${activity.worst_trade.ticket} · ${fmtMoney(activity.worst_trade.net_pnl)}` : '—',
			tone: 'text-accent-loss'
		},
		{ label: 'Max Win Streak', value: `${activity.max_win_streak}` },
		{ label: 'Max Loss Streak', value: `${activity.max_loss_streak}` }
	]);

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
						data: [sel.wins, sel.losses, sel.breakeven],
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
				plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, padding: 12 } } }
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
		[sel.wins, sel.losses, sel.breakeven].join(',');
		if (canvas) render();
	});

	onDestroy(() => {
		chart?.destroy();
		chart = null;
	});

	const card =
		'rounded-xl border border-slate-200 bg-white p-4 shadow-card dark:border-white/[0.07] dark:bg-surface-900';
	const pill = (active: boolean): string =>
		`rounded-lg px-4 py-1.5 text-sm font-semibold transition-all duration-150 focus-visible:outline-emerald-500 active:scale-95 ${active ? 'bg-emerald-500 text-white shadow-lift' : 'text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white'}`;
	const row =
		'flex items-baseline justify-between gap-3 border-b border-zinc-200/70 py-1.5 font-mono text-[13px] tabular-nums last:border-0 dark:border-zinc-800/80';
</script>

<section class={card} aria-label="Long short analysis">
	<div class="mb-3 flex flex-wrap items-center gap-2">
		<h2 class="text-[13px] font-semibold tracking-tight">Long / Short Analysis</h2>
		<div class="ml-auto flex rounded-xl border border-slate-200 p-1 dark:border-white/10" role="group" aria-label="Direction filter">
			<button type="button" class={pill(side === 'all')} onclick={() => (side = 'all')}>All</button>
			<button type="button" class={pill(side === 'long')} onclick={() => (side = 'long')}>Long</button>
			<button type="button" class={pill(side === 'short')} onclick={() => (side = 'short')}>Short</button>
		</div>
	</div>

	<div class="grid grid-cols-1 gap-4 md:grid-cols-3">
		<div class="h-64"><canvas bind:this={canvas}></canvas></div>
		<div>
			<h3 class="mb-1 text-xs font-semibold tracking-wide text-emerald-600 uppercase dark:text-emerald-400">Win Statistics</h3>
			<dl>
				{#each winRows as r}
					<div class={row}>
						<dt class="font-sans text-xs text-slate-500 dark:text-slate-400">{r.label}</dt>
						<dd class="font-semibold">{r.value}</dd>
					</div>
				{/each}
			</dl>
		</div>
		<div>
			<h3 class="mb-1 text-xs font-semibold tracking-wide text-rose-600 uppercase dark:text-rose-400">Loss Statistics</h3>
			<dl>
				{#each lossRows as r}
					<div class={row}>
						<dt class="font-sans text-xs text-slate-500 dark:text-slate-400">{r.label}</dt>
						<dd class="font-semibold">{r.value}</dd>
					</div>
				{/each}
			</dl>
		</div>
	</div>

	<h3 class="mt-4 mb-2 text-[13px] font-semibold tracking-tight">Performance Overview</h3>
	<div class="grid grid-cols-2 gap-2 sm:grid-cols-3">
		{#each overview as o}
			<div class="rounded-lg border border-slate-200 p-2.5 dark:border-white/[0.07] dark:bg-white/[0.02]">
				<p class="text-[11px] text-slate-500 dark:text-slate-400">{o.label}</p>
				<p class="font-mono text-sm font-bold tabular-nums {o.tone ?? ''}">{o.value}</p>
			</div>
		{/each}
	</div>
	<p class="mt-2 font-mono text-[11px] text-slate-500 tabular-nums dark:text-slate-500">
		{sel.trades} trades · {sel.win_rate.toFixed(1)}% win rate
	</p>
</section>
