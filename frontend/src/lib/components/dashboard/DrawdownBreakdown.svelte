<script lang="ts">
	import type { DrawdownBreakdown } from '$lib/api';
	import { fmtMoney, pnlTone, toneText } from '$lib/utils/format';

	const {
		account,
		setup
	}: { account: DrawdownBreakdown; setup: DrawdownBreakdown } = $props();

	const cards = $derived([
		{ title: 'By account', data: account },
		{ title: 'By setup', data: setup }
	]);

	const th =
		'px-3 py-2 text-right text-[10px] font-medium uppercase tracking-[0.12em] text-dim';
	const td = 'px-3 py-2 text-right font-mono text-[12px] tabular-nums';

	function ddTone(v: number): string {
		return v === 0 ? 'text-dim' : 'text-loss';
	}
</script>

<section class="grid grid-cols-1 gap-3 lg:grid-cols-2" aria-label="Drawdown by group">
	{#each cards as card (card.title)}
		<div class="card rise p-5">
			<div class="flex flex-wrap items-baseline justify-between gap-2">
				<h3 class="eyebrow">Drawdown · {card.title.toLowerCase()}</h3>
				<span class="num text-[11px] text-dim">
					{card.data.groups.length} groups · worst {fmtMoney(card.data.overall.max_drawdown)}
				</span>
			</div>

			{#if card.data.groups.length === 0}
				<p class="py-8 text-center text-sm text-mut">No closed trades to measure.</p>
			{:else}
				<div class="mt-3 overflow-x-auto">
					<table class="w-full min-w-[28rem] border-collapse text-left">
						<thead>
							<tr class="border-b border-line">
								<th
									class="px-1 py-2 text-left text-[10px] font-medium uppercase tracking-[0.12em] text-dim"
									scope="col">{card.data.group_by === 'account' ? 'Account' : 'Setup'}</th
								>
								<th class={th} scope="col">Trades</th>
								<th class={th} scope="col">Net</th>
								<th class={th} scope="col">Max DD</th>
								<th class={th} scope="col">Now</th>
							</tr>
						</thead>
						<tbody>
							<tr class="border-b border-line/60 bg-raised/30">
								<th class="px-1 py-2 text-left text-[11px] font-semibold whitespace-nowrap text-fg" scope="row">
									{card.data.overall.label}
								</th>
								<td class="{td} text-fg">{card.data.overall.trade_count}</td>
								<td class="{td} font-semibold {toneText[pnlTone(card.data.overall.net_pnl)]}">
									{fmtMoney(card.data.overall.net_pnl)}
								</td>
								<td class="{td} {ddTone(card.data.overall.max_drawdown)}">
									{card.data.overall.max_drawdown === 0
										? '—'
										: fmtMoney(card.data.overall.max_drawdown)}
								</td>
								<td class="{td} {ddTone(card.data.overall.current_drawdown)}">
									{card.data.overall.current_drawdown === 0
										? 'at peak'
										: fmtMoney(card.data.overall.current_drawdown)}
								</td>
							</tr>
							{#each card.data.groups as group (group.key)}
								<tr class="border-b border-line/60 transition-colors last:border-0 hover:bg-raised/40">
									<th class="px-1 py-2 text-left text-[11.5px] font-medium whitespace-nowrap text-fg" scope="row">
										{group.label}
									</th>
									<td class="{td} text-fg">{group.trade_count}</td>
									<td class="{td} {toneText[pnlTone(group.net_pnl)]}">{fmtMoney(group.net_pnl)}</td>
									<td class="{td} {ddTone(group.max_drawdown)}">
										{group.max_drawdown === 0 ? '—' : fmtMoney(group.max_drawdown)}
									</td>
									<td class="{td} {ddTone(group.current_drawdown)}">
										{group.current_drawdown === 0
											? 'at peak'
											: fmtMoney(group.current_drawdown)}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
		</div>
	{/each}
</section>
