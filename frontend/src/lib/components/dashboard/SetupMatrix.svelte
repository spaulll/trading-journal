<script lang="ts">
	import type { SetupMatrix, SetupMatrixRow } from '$lib/api';
	import { fmtMoney, fmtNum, pnlTone, toneText } from '$lib/utils/format';

	const { data }: { data: SetupMatrix } = $props();

	function cell(row: SetupMatrixRow, symbol: string) {
		return row.cells.find((c) => c.symbol === symbol);
	}
</script>

<section class="min-w-0" aria-label="Setup by symbol matrix">
	<div class="flex flex-wrap items-baseline justify-between gap-2">
		<h3 class="eyebrow">Setup × symbol</h3>
		<span class="num text-[11px] text-dim">
			{data.rows.length} setups · {data.symbols.length} symbols
		</span>
	</div>

	{#if data.rows.length === 0}
		<p class="py-8 text-center text-sm text-mut">
			Tag a closed trade with a setup to build the matrix.
		</p>
	{:else}
		<div class="mt-3 overflow-x-auto">
			<table class="w-full border-collapse text-left">
				<thead>
					<tr class="border-b border-line">
						<th
							class="sticky left-0 z-10 bg-panel px-2 py-2 text-left text-[10px] font-medium uppercase tracking-[0.12em] text-dim"
							scope="col">Setup</th
						>
						{#each data.symbols as symbol (symbol)}
							<th
								class="px-2 py-2 text-right font-mono text-[10px] font-medium uppercase tracking-[0.08em] text-dim whitespace-nowrap"
								scope="col">{symbol}</th
							>
						{/each}
						<th
							class="px-2 py-2 text-right text-[10px] font-medium uppercase tracking-[0.12em] text-dim"
							scope="col">Total</th
						>
					</tr>
				</thead>
				<tbody>
					{#each data.rows as row (row.label)}
						<tr class="group border-b border-line transition-colors hover:bg-raised/40">
							<th
								class="sticky left-0 z-10 bg-panel px-2 py-2 text-left text-[12px] font-semibold whitespace-nowrap text-fg group-hover:bg-raised"
								scope="row"
							>
								{#if row.is_untagged}
									<span class="text-dim">{row.label}</span>
								{:else}
									<span class="font-mono text-[11px] text-dim">#</span>{row.label}
								{/if}
								<span class="ml-2 font-mono text-[10px] font-normal text-dim tabular-nums">
									{row.trade_count}t
								</span>
							</th>
							{#each data.symbols as symbol (symbol)}
								{@const c = cell(row, symbol)}
								<td class="px-2 py-2 text-right align-top whitespace-nowrap">
									{#if c}
										<span
											class="block font-mono text-[11.5px] font-semibold tabular-nums {toneText[
												pnlTone(c.net_pnl)
											]}">{fmtMoney(c.net_pnl)}</span
										>
										<span class="block font-mono text-[9.5px] text-dim tabular-nums"
											>{c.trade_count}t · {fmtNum(c.win_rate, 0)}%</span
										>
									{:else}
										<span class="text-[11px] text-dim">—</span>
									{/if}
								</td>
							{/each}
							<td
								class="px-2 py-2 text-right align-top whitespace-nowrap font-mono text-[11.5px] font-semibold tabular-nums {toneText[
									pnlTone(row.net_pnl)
								]}"
							>
								{fmtMoney(row.net_pnl)}
							</td>
						</tr>
					{/each}
				</tbody>
				<tfoot>
					<tr class="border-t border-line">
						<th
							class="sticky left-0 z-10 bg-panel px-2 pt-2 text-left text-[10px] font-semibold uppercase tracking-[0.12em] text-dim"
							scope="row">All setups</th
						>
						{#each data.column_totals as col (col.symbol)}
							<td
								class="px-2 pt-2 text-right font-mono text-[11.5px] font-semibold tabular-nums whitespace-nowrap {toneText[
									pnlTone(col.net_pnl)
								]}"
							>
								{fmtMoney(col.net_pnl)}
								<span class="block text-[9.5px] font-normal text-dim">{col.trade_count}t</span>
							</td>
						{/each}
						<td
							class="px-2 pt-2 text-right font-mono text-[11.5px] font-semibold tabular-nums whitespace-nowrap {toneText[
								pnlTone(data.grand_total.net_pnl)
							]}"
						>
							{fmtMoney(data.grand_total.net_pnl)}
							<span class="block text-[9.5px] font-normal text-dim"
								>{data.grand_total.trade_count}t</span
							>
						</td>
					</tr>
				</tfoot>
			</table>
		</div>
		<p class="mt-2 text-[11px] text-dim">
			A trade tagged with two setups counts in both rows, so rows overlap; the totals row
			counts every trade once.
		</p>
	{/if}
</section>
