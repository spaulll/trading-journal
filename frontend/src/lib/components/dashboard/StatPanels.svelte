<script lang="ts">
	import type { ActivityStreaks } from '$lib/api';
	import { fmtMoney, fmtNum } from '$lib/utils/format';
	import { countup } from '$lib/utils/motion';

	const { activity }: { activity: ActivityStreaks } = $props();

	const int = (v: number) => `${Math.round(v)}`;

	const streakRows = $derived([
		{ label: 'Max win streak', raw: activity.max_win_streak, format: int },
		{ label: 'Max loss streak', raw: activity.max_loss_streak, format: int },
		{ label: 'Max winning days', raw: activity.max_winning_days, format: int },
		{ label: 'Max losing days', raw: activity.max_losing_days, format: int },
		{ label: 'Avg win streak', raw: activity.avg_win_streak, format: (v: number) => fmtNum(v) },
		{ label: 'Avg loss streak', raw: activity.avg_loss_streak, format: (v: number) => fmtNum(v) }
	]);

	const activityRows = $derived([
		{ label: 'Total trades', raw: activity.total_trades, format: int, tone: '' },
		{ label: 'Winning trades', raw: activity.winning_trades, format: int, tone: 'text-win' },
		{ label: 'Losing trades', raw: activity.losing_trades, format: int, tone: 'text-loss' },
		{ label: 'Open trades', raw: activity.open_trades, format: int, tone: '' },
		{ label: 'Trading days', raw: activity.trading_days, format: int, tone: '' },
		{ label: 'Avg daily volume', raw: activity.avg_daily_volume, format: (v: number) => `${fmtNum(v, 3)} lots`, tone: '' },
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
	<div class="card rise p-5">
		<h3 class="eyebrow mb-2">Streaks &amp; patterns</h3>
		<dl>
			{#each streakRows as r, i}
				<div class="anim-fade {row}" style="animation-delay: {i * 45}ms">
					<dt class="text-[13px] text-mut">{r.label}</dt>
					<dd class="num text-[13px] font-semibold text-fg" use:countup={{ value: r.raw, format: r.format }}>{r.format(r.raw)}</dd>
				</div>
			{/each}
		</dl>
	</div>
	<div class="card rise p-5" style="animation-delay: 90ms">
		<h3 class="eyebrow mb-2">Trading activity</h3>
		<dl>
			{#each activityRows as r, i}
				<div class="anim-fade {row}" style="animation-delay: {90 + i * 45}ms">
					<dt class="text-[13px] text-mut">{r.label}</dt>
					{#if 'raw' in r && r.format}
						<dd class="num text-[13px] font-semibold {r.tone}" use:countup={{ value: r.raw, format: r.format }}>{r.format(r.raw)}</dd>
					{:else}
						<dd class="num text-[13px] font-semibold {r.tone}">{r.value}</dd>
					{/if}
				</div>
			{/each}
		</dl>
	</div>
</section>
