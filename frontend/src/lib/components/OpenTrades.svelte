<script lang="ts">
	import { fade } from 'svelte/transition';
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

	const LADDER = [
		{ key: 'entry', label: 'Entry', get: (t: TradeDto) => t.entry_price },
		{ key: 'stop', label: 'Stop', get: (t: TradeDto) => t.current_sl ?? t.initial_sl },
		{ key: 'target', label: 'Target', get: (t: TradeDto) => t.tp }
	] as const;
</script>

<section aria-label="Open positions" class="rise" style="animation-delay: 60ms">
	<header class="mb-3 flex items-baseline justify-between gap-3">
		<div class="flex items-center gap-2.5">
			<span class="h-1.5 w-1.5 rounded-full bg-win dot-live" aria-hidden="true"></span>
			<h2 class="eyebrow">Live positions</h2>
		</div>
		<span class="num text-xs text-mut">{$openTrades.length} open</span>
	</header>

	{#if $openTrades.length === 0}
		<div
			class="card border-dashed px-5 py-6 text-center text-sm leading-relaxed text-mut"
		>
			No open positions — new bot or web entries land here live.
		</div>
	{:else}
		<div class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3" transition:fade={FADE}>
			{#each $openTrades as t, i (t.id)}
				{@const isShort = (t.direction ?? '').toLowerCase() === 'sell'}
				<div
					role="button"
					tabindex={0}
					onclick={() => openTrade(t.id)}
					onkeydown={(e) => e.key === 'Enter' && openTrade(t.id)}
					class="card card-hover group relative overflow-hidden p-4 text-left focus-visible:outline-none"
					style="animation: rise 0.6s cubic-bezier(0.22, 1, 0.36, 1) {Math.min(i, 8) * 70}ms both;"
				>
					<span
						class="absolute inset-y-0 left-0 w-[3px] {isShort ? 'bg-loss/70' : 'bg-win/70'}"
						aria-hidden="true"
					></span>

					<div class="flex items-center justify-between gap-2 pl-1.5">
						<span class="num text-[15px] font-semibold tracking-tight text-fg uppercase">
							{t.symbol ?? '—'}
						</span>
						<span
							class="rounded-lg px-2 py-0.5 font-mono text-[10px] font-semibold tracking-[0.14em] uppercase {isShort
								? 'bg-loss/12 text-loss'
								: 'bg-win/12 text-win'}"
						>
							{t.direction ?? '—'}
						</span>
					</div>

					<dl class="mt-3.5 grid grid-cols-3 gap-2 pl-1.5">
						{#each LADDER as col}
							<div class="min-w-0">
								<dt class="eyebrow">{col.label}</dt>
								<dd class="num mt-1 truncate text-[13px] text-fg">
									{fmtNum(col.get(t), 2)}
								</dd>
							</div>
						{/each}
					</dl>

					<div
						class="mt-3.5 flex items-center justify-between gap-2 border-t border-line pt-3 pl-1.5"
					>
						<span class="num truncate text-[11.5px] text-dim">
							{t.size ?? '—'} lots · risk {fmtNum(riskDist(t), 2)}
						</span>
						<span class="flex shrink-0 items-center gap-2">
							<span class="num text-[13px] font-semibold {toneText[pnlTone(t.net_pnl)]}">
								{fmtMoney(t.net_pnl)}
							</span>
							<button
								type="button"
								onclick={(e) => {
									e.stopPropagation();
									requestClose(t.id);
								}}
								class="rounded-lg border border-line px-2.5 py-1 font-mono text-[10px] font-bold tracking-[0.12em] uppercase text-loss transition-all duration-200 hover:border-loss/50 hover:bg-loss/12 focus-visible:outline-none active:scale-95"
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
