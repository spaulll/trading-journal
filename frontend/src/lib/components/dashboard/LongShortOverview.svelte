<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { Chart, registerables } from 'chart.js';
	import type { ActivityStreaks, DirectionStats } from '$lib/api';
	import { fmtMoney } from '$lib/utils/format';
	import { palette } from '$lib/utils/palette';
	import { theme } from '$lib/stores/theme';

	Chart.register(...registerables);

	const {
		longShort,
		activity
	}: {
		longShort: { buy: DirectionStats; sell: DirectionStats; all?: DirectionStats };
		activity: ActivityStreaks;
	} = $props();

	let side = $state<'all' | 'long' | 'short'>('all');

	// Long ↔ buy, Short ↔ sell. `all` comes from the server (correct durations
	// + side-aware streaks); the manual fallback only runs for stale payloads.
	const sel = $derived.by((): DirectionStats => {
		if (side === 'long') return longShort.buy;
		if (side === 'short') return longShort.sell;
		if (longShort.all) return longShort.all;
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
		const avgWinDur =
			wins && b.avg_win_duration_min !== null && s.avg_win_duration_min !== null
				? (b.avg_win_duration_min * b.wins + s.avg_win_duration_min * s.wins) / wins
				: (b.avg_win_duration_min ?? s.avg_win_duration_min);
		const avgLossDur =
			losses && b.avg_loss_duration_min !== null && s.avg_loss_duration_min !== null
				? (b.avg_loss_duration_min * b.losses + s.avg_loss_duration_min * s.losses) / losses
				: (b.avg_loss_duration_min ?? s.avg_loss_duration_min);
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
			avg_win_duration_min: avgWinDur ?? null,
			avg_loss_duration_min: avgLossDur ?? null,
			max_win_streak: Math.max(b.max_win_streak, s.max_win_streak),
			max_loss_streak: Math.max(b.max_loss_streak ?? 0, s.max_loss_streak ?? 0)
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
		{ label: 'Total winners', value: `${sel.wins}` },
		{ label: 'Best win', value: sel.best ? `${sel.best.ticket} · ${fmtMoney(sel.best.net_pnl)}` : '—' },
		{ label: 'Average win', value: fmtMoney(sel.avg_win) },
		{ label: 'Avg win duration', value: fmtDur(sel.avg_win_duration_min) },
		{ label: 'Max win streak', value: `${sel.max_win_streak}` }
	]);
	const lossRows = $derived([
		{ label: 'Total losers', value: `${sel.losses}` },
		{ label: 'Worst loss', value: sel.worst ? `${sel.worst.ticket} · ${fmtMoney(sel.worst.net_pnl)}` : '—' },
		{ label: 'Average loss', value: fmtMoney(sel.avg_loss) },
		{ label: 'Avg loss duration', value: fmtDur(sel.avg_loss_duration_min) },
		{ label: 'Max loss streak', value: `${sel.max_loss_streak ?? activity.max_loss_streak}` }
	]);

	const overview = $derived([
		{ label: 'Average win', value: fmtMoney(sel.avg_win), tone: 'text-win' },
		{ label: 'Average loss', value: fmtMoney(sel.avg_loss), tone: 'text-loss' },
		{
			label: 'Best trade',
			value: activity.best_trade ? `${activity.best_trade.ticket} · ${fmtMoney(activity.best_trade.net_pnl)}` : '—',
			tone: 'text-win'
		},
		{
			label: 'Worst trade',
			value: activity.worst_trade ? `${activity.worst_trade.ticket} · ${fmtMoney(activity.worst_trade.net_pnl)}` : '—',
			tone: 'text-loss'
		},
		{ label: 'Max win streak', value: `${activity.max_win_streak}`, tone: 'text-fg' },
		{ label: 'Max loss streak', value: `${activity.max_loss_streak}`, tone: 'text-fg' }
	]);

	let canvas: HTMLCanvasElement | null = null;
	let chart: Chart | null = null;

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
						data: [sel.wins, sel.losses, sel.breakeven],
						backgroundColor: [p.win, p.loss, p.flat],
						borderColor: p.panel,
						borderWidth: 3,
						hoverOffset: 8
					}
				]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				cutout: '70%',
				animation: { duration: 850, easing: 'easeOutQuart', animateRotate: true },
				plugins: {
					legend: {
						position: 'bottom',
						labels: {
							color: p.axis,
							usePointStyle: true,
							pointStyle: 'circle',
							boxWidth: 8,
							padding: 12,
							font: { family: 'Geist', size: 11 }
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
		[sel.wins, sel.losses, sel.breakeven].join(',');
		void $theme;
		if (canvas) render();
	});

	onDestroy(() => {
		chart?.destroy();
		chart = null;
	});

	const row =
		'flex items-baseline justify-between gap-3 border-b border-line py-1.5 last:border-0';
</script>

<section class="card p-5" aria-label="Long short analysis">
	<div class="mb-5 flex flex-wrap items-center gap-3">
		<h2 class="eyebrow">Long / short analysis</h2>
		<p class="num text-[11.5px] text-dim">{sel.trades} trades · {sel.win_rate.toFixed(1)}% win rate</p>
		<div class="ml-auto flex rounded-xl border border-line bg-raised/50 p-1" role="group" aria-label="Direction filter">
			{#each (['all', 'long', 'short'] as const) as s}
				<button
					type="button"
					class="chip px-4 py-1.5 text-[13px] font-semibold"
					data-active={side === s}
					onclick={() => (side = s)}
				>
					{s === 'all' ? 'All' : s === 'long' ? 'Long' : 'Short'}
				</button>
			{/each}
		</div>
	</div>

	<div class="grid grid-cols-1 gap-5 lg:grid-cols-12">
		<div class="lg:col-span-4 xl:col-span-3">
			<div class="h-60 min-w-0"><canvas bind:this={canvas}></canvas></div>
		</div>
		<div class="min-w-0 lg:col-span-4 xl:col-span-4">
			<h3 class="eyebrow mb-1 text-win">Win statistics</h3>
			<dl>
				{#each winRows as r}
					<div class={row}>
						<dt class="text-xs text-mut">{r.label}</dt>
						<dd class="num text-[13px] font-semibold text-fg">{r.value}</dd>
					</div>
				{/each}
			</dl>
		</div>
		<div class="min-w-0 lg:col-span-4 xl:col-span-5">
			<h3 class="eyebrow mb-1 text-loss">Loss statistics</h3>
			<dl>
				{#each lossRows as r}
					<div class={row}>
						<dt class="text-xs text-mut">{r.label}</dt>
						<dd class="num text-[13px] font-semibold text-fg">{r.value}</dd>
					</div>
				{/each}
			</dl>
		</div>
	</div>

	<h3 class="eyebrow mt-6 mb-2">Performance overview</h3>
	<div class="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">
		{#each overview as o}
			<div class="rounded-xl border border-line bg-raised/50 p-3">
				<p class="text-[11px] text-dim">{o.label}</p>
				<p class="num mt-0.5 text-sm leading-tight font-bold wrap-break-word {o.tone}">{o.value}</p>
			</div>
		{/each}
	</div>
</section>
