<script lang="ts">
	import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-svelte';
	import type { KpiDashboard } from '$lib/api';
	import { fmtMoney } from '$lib/utils/format';
	import { countup } from '$lib/utils/motion';

	const { kpi }: { kpi: KpiDashboard } = $props();

	const META = [
		{ key: 'london', label: 'London', hours: '7 AM – 1 PM UTC', accent: 'from-accent/18' },
		{ key: 'new_york', label: 'New York', hours: '1 PM – 10 PM UTC', accent: 'from-win/18' },
		{ key: 'asia', label: 'Asia', hours: '12 AM – 6 AM UTC', accent: 'from-flat/20' },
		{ key: 'outside', label: 'Outside', hours: 'Off-killzone', accent: 'from-loss/14' }
	] as const;
</script>

<section class="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Session performance">
	{#each META as m, i (m.key)}
		{@const s = kpi.sessions[m.key] ?? { net_pnl: 0, trade_count: 0, win_rate: 0, return_pct: 0 }}
		{@const up = s.net_pnl > 0}
		{@const flat = s.net_pnl === 0}
		<div
			class="card card-hover relative overflow-hidden p-5"
			style="animation: rise 0.6s cubic-bezier(0.22, 1, 0.36, 1) {i * 60}ms both;"
		>
			<span
				class="pointer-events-none absolute inset-x-0 top-0 h-24 bg-gradient-to-b to-transparent {m.accent}"
				aria-hidden="true"
			></span>

			<div class="relative flex items-baseline justify-between gap-2">
				<h3 class="text-[13.5px] font-semibold text-fg">{m.label}</h3>
				<span class="num text-[10.5px] text-dim">{m.hours}</span>
			</div>

			<p
				class="relative mt-2 flex items-center gap-1 text-[1.65rem] leading-none tabular-nums {flat
					? 'text-dim'
					: up
						? 'text-win'
						: 'text-loss'}"
			>
				<span class="display" use:countup={{ value: Math.abs(s.return_pct), format: (v) => `${v.toFixed(2)}%` }}>
					{Math.abs(s.return_pct).toFixed(2)}%
				</span>
				{#if !flat}
					{#if up}
						<ArrowUpRight size={17} strokeWidth={2.2} aria-hidden="true" />
					{:else}
						<ArrowDownRight size={17} strokeWidth={2.2} aria-hidden="true" />
					{/if}
				{:else}
					<Minus size={17} strokeWidth={2.2} aria-hidden="true" />
				{/if}
				<span class="eyebrow ml-0.5 self-end pb-0.5">{up ? 'profit' : flat ? 'flat' : 'loss'}</span>
			</p>

			<div class="relative mt-3 flex items-center gap-2.5 border-t border-line pt-3 font-mono text-[11.5px] tabular-nums">
				<span class="{flat ? 'text-dim' : up ? 'text-win' : 'text-loss'}">{fmtMoney(s.net_pnl)}</span>
				<span class="text-dim/60">·</span>
				<span class="text-mut">{s.trade_count} trades</span>
				<span class="text-dim/60">·</span>
				<span class="text-mut">{s.win_rate.toFixed(0)}% WR</span>
			</div>
		</div>
	{/each}
</section>
