<script lang="ts">
	import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-svelte';
	import type { KpiDashboard } from '$lib/api';
	import { fmtMoney } from '$lib/utils/format';

	const { kpi }: { kpi: KpiDashboard } = $props();

	const META = [
		{ key: 'london', label: 'London', hours: '7 AM – 1 PM UTC' },
		{ key: 'new_york', label: 'New York', hours: '1 PM – 10 PM UTC' },
		{ key: 'asia', label: 'Asia', hours: '12 AM – 6 AM UTC' },
		{ key: 'outside', label: 'Outside', hours: 'Off-killzone' }
	] as const;

	const card =
		'rounded-xl border border-slate-200 bg-white p-4 shadow-card dark:border-white/[0.07] dark:bg-surface-900';
</script>

<section class="grid grid-cols-1 gap-4 sm:grid-cols-2" aria-label="Session performance">
	{#each META as m}
		{@const s = kpi.sessions[m.key] ?? { net_pnl: 0, trade_count: 0, win_rate: 0, return_pct: 0 }}
		{@const up = s.net_pnl > 0}
		{@const flat = s.net_pnl === 0}
		<div class={card}>
			<div class="flex items-baseline justify-between gap-2">
				<h3 class="text-[13px] font-semibold tracking-tight">{m.label}</h3>
				<span class="font-mono text-[11px] text-slate-500 tabular-nums dark:text-slate-500">{m.hours}</span>
			</div>
			<p
				class="mt-1 flex items-center gap-1 font-mono text-xl font-bold tabular-nums {flat
					? 'text-slate-500 dark:text-slate-400'
					: up
						? 'text-accent-win'
						: 'text-accent-loss'}"
			>
				{#if !flat}
					{#if up}
						<ArrowUpRight size={18} strokeWidth={2.2} aria-hidden="true" />
					{:else}
						<ArrowDownRight size={18} strokeWidth={2.2} aria-hidden="true" />
					{/if}
				{:else}
					<Minus size={18} strokeWidth={2.2} aria-hidden="true" />
				{/if}
				{Math.abs(s.return_pct).toFixed(2)}% {up ? 'PROFIT' : flat ? 'FLAT' : 'LOSS'}
			</p>
			<div class="mt-2 flex items-center gap-3 font-mono text-xs tabular-nums">
				<span class={flat ? 'text-slate-500 dark:text-slate-400' : up ? 'text-accent-win' : 'text-accent-loss'}>
					{fmtMoney(s.net_pnl)}
				</span>
				<span class="text-slate-400 dark:text-slate-500">·</span>
				<span class="text-slate-500 dark:text-slate-400">{s.trade_count} trades</span>
				<span class="text-slate-400 dark:text-slate-500">·</span>
				<span class="text-slate-500 dark:text-slate-400">{s.win_rate.toFixed(0)}% WR</span>
			</div>
		</div>
	{/each}
</section>
