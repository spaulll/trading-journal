<script lang="ts">
	import type { ActivityStreaks } from '$lib/api';
	import { fmtMoney, fmtNum } from '$lib/utils/format';

	const { activity }: { activity: ActivityStreaks } = $props();

	const streakRows = $derived([
		{ label: 'Max Win Streak', value: `${activity.max_win_streak}` },
		{ label: 'Max Loss Streak', value: `${activity.max_loss_streak}` },
		{ label: 'Max Winning Days', value: `${activity.max_winning_days}` },
		{ label: 'Max Losing Days', value: `${activity.max_losing_days}` },
		{ label: 'Avg Win Streak', value: fmtNum(activity.avg_win_streak) },
		{ label: 'Avg Loss Streak', value: fmtNum(activity.avg_loss_streak) }
	]);

	const activityRows = $derived([
		{ label: 'Total Trades', value: `${activity.total_trades}` },
		{ label: 'Winning Trades', value: `${activity.winning_trades}`, tone: 'text-accent-win' },
		{ label: 'Losing Trades', value: `${activity.losing_trades}`, tone: 'text-accent-loss' },
		{ label: 'Open Trades', value: `${activity.open_trades}` },
		{ label: 'Trading Days', value: `${activity.trading_days}` },
		{ label: 'Avg Daily Volume', value: `${fmtNum(activity.avg_daily_volume, 3)} lots` },
		{
			label: 'Best Trade',
			value: activity.best_trade ? `${activity.best_trade.ticket} · ${fmtMoney(activity.best_trade.net_pnl)}` : '—',
			tone: 'text-accent-win'
		},
		{
			label: 'Worst Trade',
			value: activity.worst_trade ? `${activity.worst_trade.ticket} · ${fmtMoney(activity.worst_trade.net_pnl)}` : '—',
			tone: 'text-accent-loss'
		}
	]);

	const card =
		'rounded-xl border border-slate-200 bg-white p-4 shadow-card dark:border-white/[0.07] dark:bg-surface-900';
	const row =
		'flex items-baseline justify-between gap-3 border-b border-zinc-200/70 py-2 font-mono text-sm tabular-nums last:border-0 dark:border-zinc-800/80';
</script>

<section class="grid grid-cols-1 gap-4 md:grid-cols-2" aria-label="Streaks and activity">
	<div class={card}>
		<h3 class="mb-1 text-[13px] font-semibold tracking-tight">Streaks &amp; Patterns</h3>
		<dl>
			{#each streakRows as r}
				<div class={row}>
					<dt class="font-sans text-[13px] text-slate-500 dark:text-slate-400">{r.label}</dt>
					<dd class="font-semibold">{r.value}</dd>
				</div>
			{/each}
		</dl>
	</div>
	<div class={card}>
		<h3 class="mb-1 text-[13px] font-semibold tracking-tight">Trading Activity</h3>
		<dl>
			{#each activityRows as r}
				<div class={row}>
					<dt class="font-sans text-[13px] text-slate-500 dark:text-slate-400">{r.label}</dt>
					<dd class="font-semibold {r.tone ?? ''}">{r.value}</dd>
				</div>
			{/each}
		</dl>
	</div>
</section>
