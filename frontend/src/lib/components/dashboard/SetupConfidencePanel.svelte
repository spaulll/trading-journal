<script lang="ts">
	import type { SetupConfidence, SetupConfidenceRow } from '$lib/api';
	import { fmtMoney, fmtNum, pnlTone, toneText } from '$lib/utils/format';

	const { data }: { data: SetupConfidence } = $props();

	const th =
		'px-3 py-2 text-right text-[10px] font-medium uppercase tracking-[0.12em] text-dim';
	const td = 'px-3 py-2 text-right font-mono text-[12px] tabular-nums';

	/** A shared axis so the range bars are comparable across rows. */
	const domain = $derived.by(() => {
		const values = data.tags
			.flatMap((t) => [t.ci_low, t.ci_high])
			.filter((v): v is number => v !== null);
		if (values.length === 0) return { min: -1, span: 2 };
		const min = Math.min(0, ...values);
		const max = Math.max(0, ...values);
		return { min, span: max - min || 1 };
	});

	function pos(v: number): number {
		return ((v - domain.min) / domain.span) * 100;
	}

	function ciTitle(t: SetupConfidenceRow): string {
		if (t.ci_low === null || t.ci_high === null) return 'Not enough trades for an interval';
		return `${Math.round(t.ci_level * 100)}% CI: ${fmtMoney(t.ci_low)} to ${fmtMoney(t.ci_high)}`;
	}
</script>

<section class="card rise p-5" aria-label="Setup expectancy confidence">
	<div class="flex flex-wrap items-baseline justify-between gap-2">
		<h2 class="eyebrow">Setup expectancy · confidence</h2>
		<span class="num text-[11px] text-dim">
			min sample {data.min_sample} · {Math.round(data.ci_level * 100)}% interval
		</span>
	</div>

	{#if data.tags.length === 0}
		<p class="py-8 text-center text-sm text-mut">
			Tag a closed trade with a setup to measure its expectancy.
		</p>
	{:else}
		<div class="mt-3 overflow-x-auto">
			<table class="w-full min-w-[44rem] border-collapse text-left">
				<thead>
					<tr class="border-b border-line">
						<th
							class="px-1 py-2 text-left text-[10px] font-medium uppercase tracking-[0.12em] text-dim"
							scope="col">Setup</th
						>
						<th class={th} scope="col">Trades</th>
						<th class={th} scope="col">Win %</th>
						<th class={th} scope="col">Expectancy</th>
						<th class="px-3 py-2 text-left text-[10px] font-medium uppercase tracking-[0.12em] text-dim" scope="col"
							>Interval</th
						>
						<th class={th} scope="col">Net</th>
					</tr>
				</thead>
				<tbody>
					{#each data.tags as row (row.name)}
						<tr class="border-b border-line/60 transition-colors hover:bg-raised/40">
							<th class="px-1 py-2 text-left whitespace-nowrap" scope="row">
								<span class="font-mono text-[11px] text-dim">#</span>
								<span class="text-[12px] font-semibold text-fg">{row.name}</span>
								{#if !row.sufficient}
									<span
										class="ml-2 rounded border border-line px-1 py-px text-[9px] uppercase tracking-wide text-dim"
										title="Fewer decided trades than the configured minimum — the average is not ranked"
										>insufficient</span
									>
								{/if}
								{#if row.unpriced > 0}
									<span class="ml-2 text-[10px] text-dim">{row.unpriced} unpriced</span>
								{/if}
							</th>
							<td class="{td} text-fg">{row.trade_count}</td>
							<td class="{td} text-fg">{fmtNum(row.win_rate, 1)}</td>
							<td class="{td} {row.sufficient ? toneText[pnlTone(row.expectancy)] : 'text-mut'}">
								{fmtMoney(row.expectancy)}
							</td>
							<td class="px-3 py-2">
								<div class="flex items-center gap-2">
									<div class="relative h-1.5 w-28 overflow-hidden rounded-full bg-line/70" title={ciTitle(row)}>
										{#if row.ci_low !== null && row.ci_high !== null}
											<div
												class="absolute inset-y-0 rounded-full bg-accent/60"
												style="left: {pos(row.ci_low)}%; width: {Math.max(
													1,
													pos(row.ci_high) - pos(row.ci_low)
												)}%"
											></div>
										{/if}
										<div class="absolute inset-y-0 w-px bg-dim/70" style="left: {pos(0)}%"></div>
									</div>
									<span class="num text-[10px] whitespace-nowrap text-dim">
										{#if row.ci_low === null || row.ci_high === null}
											—
										{:else}
											{fmtMoney(row.ci_low)} … {fmtMoney(row.ci_high)}
										{/if}
									</span>
								</div>
							</td>
							<td class="{td} font-semibold {toneText[pnlTone(row.net_pnl)]}">
								{fmtMoney(row.net_pnl)}
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
		<p class="mt-2 text-[11px] text-dim">
			Ranked by the lower bound of the interval, not the average: a small sample has to
			clear zero before it outranks a larger one. {data.insufficient} of {data.tags.length}
			setups are below the minimum.
		</p>
	{/if}
</section>
