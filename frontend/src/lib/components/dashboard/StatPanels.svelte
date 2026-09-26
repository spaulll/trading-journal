<script lang="ts">
	import type { ActivityStreaks } from '$lib/api';
	import { fmtMoney, fmtNum } from '$lib/utils/format';

	const { activity }: { activity: ActivityStreaks } = $props();

	const streakRows = $derived([
		{ label: 'Max win streak', value: `${activity.max_win_streak}` },
		{ label: 'Max loss streak', value: `${activity.max_loss_streak}` },
		{ label: 'Max winning days', value: `${activity.max_winning_days}` },
		{ label: 'Max losing days', value: `${activity.max_losing_days}` },
		{ label: 'Avg win streak', value: fmtNum(activity.avg_win_streak) },
		{ label: 'Avg loss streak', value: fmtNum(activity.avg_loss_streak) }
	]);

	const activityRows = $derived([
		{ label: 'Total trades', value: `${activity.total_trades}`, tone: '' },
		{ label: 'Winning trades', value: `${activity.winning_trades}`, tone: 'text-win' },
		{ label: 'Losing trades', value: `${activity.losing_trades}`, tone: 'text-loss' },
		{ label: 'Open trades', value: `${activity.open_trades}`, tone: '' },
		{ label: 'Trading days', value: `${activity.trading_days}`, tone: '' },
		{ label: 'Avg daily volume', value: `${fmtNum(activity.avg_daily_volume, 3)} lots`, tone: '' },
		{
			label: 'Best trade',
			value: activity.best_trade ? `${activity.best_trade.ticket} · ${fmtMoney(activity.best_trade.net_pnl)}` : '—',
			tone: 'text-win'
		},
		{
			label: 'Worst trade',
			value: activity.worst_trade ? `${activity.worst_trade.ticket} · ${fmtMoney(activity.worst_trade.net_pnl)}` : '—',
			tone: 'text-loss'
		}
	]);

	const row =
		'flex items-baseline justify-between gap-3 border-b border-line py-2 last:border-0';
</script>

<section class="grid grid-cols-1 gap-3 md:grid-cols-2" aria-label="Streaks and activity">
	<div class="card p-5">
		<h3 class="eyebrow mb-2">Streaks &amp; patterns</h3>
		<dl>
			{#each streakRows as r}
				<div class={row}>
					<dt class="text-[13px] text-mut">{r.label}</dt>
					<dd class="num text-[13px] font-semibold text-fg">{r.value}</dd>
				</div>
			{/each}
		</dl>
	</div>
	<div class="card p-5">
		<h3 class="eyebrow mb-2">Trading activity</h3>
		<dl>
			{#each activityRows as r}
				<div class={row}>
					<dt class="text-[13px] text-mut">{r.label}</dt>
					<dd class="num text-[13px] font-semibold {r.tone}">{r.value}</dd>
				</div>
			{/each}
		</dl>
	</div>
</section>
