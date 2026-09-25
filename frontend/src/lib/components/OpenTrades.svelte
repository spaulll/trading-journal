<script lang="ts">
	import { fade } from 'svelte/transition';
	import { Crosshair, Shield, Target } from 'lucide-svelte';
	import { openTrades, openTrade, requestClose } from '$lib/stores/trades';
	import { fmtMoney, fmtNum, pnlTone, toneText } from '$lib/utils/format';
	import { FADE } from '$lib/utils/transitions';
	import type { TradeDto } from '$lib/api';

	function riskDist(t: TradeDto): number | null {
		const stop = t.current_sl ?? t.initial_sl;
		if (t.entry_price === null || stop === null || t.entry_price === undefined || stop === undefined)
			return null;
		return Math.abs(t.entry_price - stop);
	}
</script>

<section aria-label="Open positions">
	<div class="mb-3 flex items-baseline justify-between">
		<h2 class="text-sm font-semibold tracking-tight text-balance">Open positions</h2>
		<span class="font-mono text-xs tabular-nums text-slate-400 dark:text-slate-500">
			{$openTrades.length} open
		</span>
	</div>

	{#if $openTrades.length === 0}
		<div
			class="rounded-xl border border-slate-200 bg-white/60 px-5 py-4 text-sm leading-relaxed text-slate-500 shadow-card dark:border-white/[0.07] dark:bg-surface-900/60 dark:text-slate-400"
		>
			No open positions. New bot or web entries appear here live.
		</div>
	{:else}
		<div class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3" transition:fade={FADE}>
			{#each $openTrades as t, i (t.id)}
				<div
					role="button"
					tabindex={0}
					onclick={() => openTrade(t.id)}
					onkeydown={(e) => e.key === 'Enter' && openTrade(t.id)}
					style="animation-delay: {Math.min(i, 8) * 40}ms"
					class="group rounded-xl border border-slate-200 bg-white p-4 text-left shadow-card transition-all duration-150 hover:-translate-y-0.5 hover:shadow-pop focus-visible:outline-emerald-500 active:translate-y-0 active:scale-[0.99] dark:border-white/[0.07] dark:bg-surface-900 dark:hover:shadow-black/40"
				>
					<div class="flex items-center justify-between gap-2">
						<span class="font-mono text-sm font-semibold tracking-tight uppercase">
							{t.symbol ?? '—'}
						</span>
						<span
							class="rounded-md px-2 py-0.5 font-mono text-[11px] font-semibold tracking-wide uppercase {(t.direction ?? '').toLowerCase() === 'sell'
								? 'bg-rose-500/10 text-rose-600 dark:text-rose-400'
								: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'}"
						>
							{t.direction ?? '—'}
						</span>
					</div>
					<div class="mt-3 grid grid-cols-3 gap-2 font-mono text-xs tabular-nums">
						<span class="flex items-center gap-1.5 text-slate-500 dark:text-slate-400">
							<Crosshair size={13} strokeWidth={1.8} aria-hidden="true" class="shrink-0" />
							{fmtNum(t.entry_price, 2)}
						</span>
						<span class="flex items-center gap-1.5 text-slate-500 dark:text-slate-400">
							<Shield size={13} strokeWidth={1.8} aria-hidden="true" class="shrink-0" />
							{fmtNum(t.current_sl ?? t.initial_sl, 2)}
						</span>
						<span class="flex items-center gap-1.5 text-slate-500 dark:text-slate-400">
							<Target size={13} strokeWidth={1.8} aria-hidden="true" class="shrink-0" />
							{fmtNum(t.tp, 2)}
						</span>
					</div>
					<div class="mt-3 flex items-center justify-between border-t border-slate-100 pt-3 text-xs dark:border-white/[0.07]">
						<span class="text-slate-500 dark:text-slate-400">
							{t.size ?? '—'} lots · risk dist {fmtNum(riskDist(t), 2)}
						</span>
						<span class="flex items-center gap-2">
							<span class="font-mono font-medium tabular-nums {toneText[pnlTone(t.net_pnl)]}">
								{fmtMoney(t.net_pnl)}
							</span>
							<button
								type="button"
								onclick={(e) => {
									e.stopPropagation();
									requestClose(t.id);
								}}
								class="h-7 rounded-lg bg-rose-500/10 px-2.5 font-mono text-[11px] font-bold uppercase tracking-wide text-rose-600 transition-all duration-150 hover:bg-rose-500 hover:text-white focus-visible:outline-rose-500 active:scale-95 dark:text-rose-400"
							>
								Close
							</button>
						</span>
					</div>
				</div>
			{/each}
		</div>
	{/if}
</section>
