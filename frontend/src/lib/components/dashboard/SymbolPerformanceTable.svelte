<script lang="ts">
	import type { SymbolPerformance } from '$lib/api';
	import { fmtMoney, fmtNum, pnlTone, rTone, toneText } from '$lib/utils/format';

	const { data }: { data: SymbolPerformance } = $props();

	const th =
		'px-3 py-2 text-right text-[10px] font-medium uppercase tracking-[0.12em] text-dim';
	const td = 'px-3 py-2 text-right font-mono text-[12px] tabular-nums';
</script>

<section class="min-w-0" aria-label="Per-symbol performance">
	<div class="flex flex-wrap items-baseline justify-between gap-2">
		<h3 class="eyebrow">Symbol performance</h3>
		<span class="num text-[11px] text-dim">
			{data.symbols.length} symbols · {data.totals.trade_count} closed
			{#if data.totals.unpriced > 0}· {data.totals.unpriced} unpriced{/if}
		</span>
	</div>

	<div class="mt-3 overflow-x-auto">
		<table class="w-full min-w-[38rem] border-collapse text-left">
			<thead>
				<tr class="border-b border-line">
					<th
						class="px-1 py-2 text-left text-[10px] font-medium uppercase tracking-[0.12em] text-dim"
						scope="col">Symbol</th
					>
					<th class={th} scope="col">Trades</th>
					<th class={th} scope="col">Win %</th>
					<th class={th} scope="col">PF</th>
					<th class={th} scope="col">Expectancy</th>
					<th class={th} scope="col">Avg R</th>
					<th class={th} scope="col">Net</th>
				</tr>
			</thead>
			<tbody>
				{#each data.symbols as row (row.symbol)}
					<tr class="border-b border-line transition-colors hover:bg-raised/40">
						<td class="px-1 py-2 whitespace-nowrap">
							<span class="font-mono text-[12px] font-semibold text-fg">{row.symbol}</span>
							{#if !row.registered}
								<span
									class="ml-2 rounded border border-line px-1 py-px text-[9px] uppercase tracking-wide text-dim"
									title="No contract size in the symbol registry — the dollar P&L is unknown"
									>no contract</span
								>
							{/if}
							{#if row.unpriced > 0}
								<span class="ml-2 text-[10px] text-dim">{row.unpriced} unpriced</span>
							{/if}
						</td>
						<td class="{td} text-fg">{row.trade_count}</td>
						<td class="{td} text-fg">{fmtNum(row.win_rate, 1)}</td>
						<td class="{td} text-fg">
							{row.profit_factor === null ? '—' : fmtNum(row.profit_factor, 2)}
						</td>
						<td class="{td} {toneText[pnlTone(row.expectancy)]}">{fmtMoney(row.expectancy)}</td>
						<td class="{td} {toneText[rTone(row.avg_r)]}">
							{row.avg_r === null ? '—' : `${fmtNum(row.avg_r, 2)}R`}
						</td>
						<td class="{td} font-semibold {toneText[pnlTone(row.net_pnl)]}">
							{fmtMoney(row.net_pnl)}
						</td>
					</tr>
				{/each}
			</tbody>
			<tfoot>
				<tr class="border-t border-line">
					<th
						class="px-1 pt-2 text-left text-[10px] font-semibold uppercase tracking-[0.12em] text-dim"
						scope="row">All symbols</th
					>
					<td class="{td} font-semibold text-fg">{data.totals.trade_count}</td>
					<td class="{td} font-semibold text-fg">{fmtNum(data.totals.win_rate, 1)}</td>
					<td class="{td} font-semibold text-fg">
						{data.totals.profit_factor === null ? '—' : fmtNum(data.totals.profit_factor, 2)}
					</td>
					<td class="{td} font-semibold {toneText[pnlTone(data.totals.expectancy)]}">
						{fmtMoney(data.totals.expectancy)}
					</td>
					<td class="{td} font-semibold {toneText[rTone(data.totals.avg_r)]}">
						{data.totals.avg_r === null ? '—' : `${fmtNum(data.totals.avg_r, 2)}R`}
					</td>
					<td class="{td} font-semibold {toneText[pnlTone(data.totals.net_pnl)]}">
						{fmtMoney(data.totals.net_pnl)}
					</td>
				</tr>
			</tfoot>
		</table>
	</div>
	<p class="mt-2 text-[11px] text-dim">
		Expectancy is per priced trade · PF = gross profit / gross loss · R is the realised
		multiple at close.
	</p>
</section>
