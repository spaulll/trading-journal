<script lang="ts">
	import type { RiskOfRuin } from '$lib/api';
	import { fmtMoney, fmtNum, pnlTone, toneText } from '$lib/utils/format';

	const { data }: { data: RiskOfRuin } = $props();

	const th =
		'px-3 py-2 text-right text-[10px] font-medium uppercase tracking-[0.12em] text-dim';
	const td = 'px-3 py-2 text-right font-mono text-[12px] tabular-nums';

	const money = (v: number | null): string =>
		v === null ? '—' : v.toLocaleString('en-US', { style: 'currency', currency: 'USD' });

	function fmtRuin(v: number | null): string {
		if (v === null) return '—';
		if (v === 0) return '0%';
		const pct = v * 100;
		if (pct < 0.01) return '<0.01%';
		return `${pct.toFixed(pct < 1 ? 2 : 1)}%`;
	}

	function ruinTone(v: number | null): string {
		if (v === null) return 'text-dim';
		if (v <= 0.01) return 'text-win';
		if (v <= 0.05) return 'text-flat';
		return 'text-loss';
	}
</script>

<section class="card rise p-5" aria-label="Risk of ruin per setup">
	<div class="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
		<h2 class="eyebrow">Risk of ruin</h2>
		<div class="num flex flex-wrap items-baseline gap-x-4 gap-y-1 text-[11px] text-dim">
			<span>
				capital
				<span class="font-semibold text-fg">{money(data.account_size)}</span>
				{#if data.account_size_source === 'explicit'}<span class="text-dim/70"> (override)</span>{/if}
			</span>
			<span>min sample {data.min_sample}</span>
			<span>diffusion estimate</span>
		</div>
	</div>

	{#if data.setups.length === 0}
		<p class="py-8 text-center text-sm text-mut">
			Tag a closed trade with a setup to estimate its risk of ruin.
		</p>
	{:else}
		<div class="mt-3 overflow-x-auto">
			<table class="w-full min-w-[46rem] border-collapse text-left">
				<thead>
					<tr class="border-b border-line">
						<th
							class="px-1 py-2 text-left text-[10px] font-medium uppercase tracking-[0.12em] text-dim"
							scope="col">Setup</th
						>
						<th class={th} scope="col">Trades</th>
						<th class={th} scope="col">Win %</th>
						<th class={th} scope="col">Payoff</th>
						<th class={th} scope="col">Risk / trade</th>
						<th class={th} scope="col">Units</th>
						<th class={th} scope="col">Ruin</th>
					</tr>
				</thead>
				<tbody>
					{#each data.setups as row (row.name)}
						<tr class="border-b border-line/60 transition-colors last:border-0 hover:bg-raised/40">
							<th class="px-1 py-2 text-left whitespace-nowrap" scope="row">
								<span class="font-mono text-[11px] text-dim">#</span>
								<span class="text-[12px] font-semibold text-fg">{row.name}</span>
								{#if !row.sufficient}
									<span
										class="ml-2 rounded border border-line px-1 py-px text-[9px] uppercase tracking-wide text-dim"
										title="Fewer decided trades than the configured minimum"
										>insufficient</span
									>
								{/if}
							</th>
							<td class="{td} text-fg">{row.trade_count}</td>
							<td class="{td} text-fg">{fmtNum(row.win_rate, 1)}</td>
							<td class="{td} text-fg">
								{row.payoff_ratio === null ? '—' : fmtNum(row.payoff_ratio, 2)}
							</td>
							<td class="{td} text-fg">
								{money(row.risk_per_trade)}
								<span class="block text-[9px] text-dim">{row.risk_source}</span>
							</td>
							<td class="{td} text-fg">
								{row.risk_units === null ? '—' : fmtNum(row.risk_units, 1)}
							</td>
							<td class="{td} font-semibold {ruinTone(row.risk_of_ruin)}">
								{fmtRuin(row.risk_of_ruin)}
							</td>
						</tr>
					{/each}
				</tbody>
				<tfoot>
					<tr class="border-t border-line">
						<th
							class="px-1 pt-2 text-left text-[10px] font-semibold uppercase tracking-[0.12em] text-dim"
							scope="row">Net P&amp;L behind the estimate</th
						>
						<td class="px-3 pt-2 text-right font-mono text-[11.5px] font-semibold tabular-nums {toneText[
							pnlTone(data.setups.reduce((sum, row) => sum + row.net_pnl, 0))
						]}" colspan="6">
							{fmtMoney(data.setups.reduce((sum, row) => sum + row.net_pnl, 0))}
							<span class="ml-2 text-[9.5px] font-normal text-dim"
								>· setups overlap when a trade carries two of them</span
							>
						</td>
					</tr>
				</tfoot>
			</table>
		</div>
		<p class="mt-2 text-[11px] text-dim">
			Ruin is the chance of losing the capital before doubling it, at the trade's own
			average risk. A book with no edge is shown at 100%; rows with no recorded risk stay
			dash. The estimate is a diffusion approximation, not a promise.
			{#if data.detail}<span class="block text-loss">{data.detail}</span>{/if}
		</p>
	{/if}
</section>
