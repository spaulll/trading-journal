<script lang="ts">
	import { Plus } from 'lucide-svelte';
	import { api, type SummaryDto } from '$lib/api';
	import OpenTrades from '$lib/components/OpenTrades.svelte';
	import PageHead from '$lib/components/PageHead.svelte';
	import StateBlock from '$lib/components/StateBlock.svelte';
	import TableSkeleton from '$lib/components/TableSkeleton.svelte';
	import TradeCloseModal from '$lib/components/TradeCloseModal.svelte';
	import TradeModal from '$lib/components/TradeModal.svelte';
	import TradeOpenModal from '$lib/components/TradeOpenModal.svelte';
	import TradeTable from '$lib/components/TradeTable.svelte';
	import { ledgerFilterQuery, ledgerHasFilter, ledgerQuery } from '$lib/stores/ledger';
	import {
		lifecycleModal,
		loadOpenPositions,
		loadTrades,
		requestOpen,
		tradeCounts,
		trades,
		tradesError,
		tradesLoading,
		tradesTotal
	} from '$lib/stores/trades';
	import { fmtMoney, fmtR, pnlTone, toneText } from '$lib/utils/format';
	import { countup } from '$lib/utils/motion';

	// The ledger asks the server for the rows it shows: a filter change is a
	// new query, not another pass over a downloaded history.
	$effect(() => {
		const query = $ledgerQuery;
		void loadTrades(false, query);
	});

	// The live positions are their own query — an open trade may sit on a
	// later page of the ledger, or outside the active filter.
	$effect(() => {
		void loadOpenPositions();
	});

	/**
	 * The ribbon reads the server's summary over the same filter.
	 *
	 * The browser holds one page of rows, so a client-side roll-up would
	 * describe the page instead of the filter — the net, the win rate and
	 * the average R have to come from the whole filtered set.
	 */
	let summary = $state<SummaryDto | null>(null);

	$effect(() => {
		const query = $ledgerFilterQuery;
		void api
			.summary(query)
			.then((s) => (summary = s))
			.catch(() => {
				// The ribbon keeps the last numbers it had.
			});
	});


	const ribbon = $derived([
		{
			label: 'Net realized',
			value: summary?.net_pnl ?? 0,
			format: (v: number) => fmtMoney(v),
			tone: toneText[pnlTone(summary?.net_pnl ?? 0)],
			hint: `${summary?.total_trades ?? 0} closed${summary?.unpriced ? ` · ${summary.unpriced} unpriced` : ''}`
		},
		{
			label: 'Win rate',
			value: summary?.win_rate ?? 0,
			format: (v: number) => `${v.toFixed(1)}%`,
			tone: 'text-fg',
			hint: `${summary?.wins ?? 0}W · ${summary?.losses ?? 0}L · ${summary?.breakeven ?? 0}BE`
		},
		{
			label: 'Average R',
			value: summary?.avg_r ?? 0,
			format: (v: number) => fmtR(v),
			tone: toneText[pnlTone(summary?.avg_r ?? 0)],
			hint: summary?.avg_r === null || summary?.avg_r === undefined ? 'no R data' : 'per closed trade'
		},
		{
			label: 'Open now',
			value: summary?.open_trades ?? 0,
			format: (v: number) => `${Math.round(v)}`,
			tone: (summary?.open_trades ?? 0) > 0 ? 'text-accent' : 'text-dim',
			hint: 'live positions'
		}
	]);
</script>

<svelte:head>
	<title>Trades · Trading Journal</title>
</svelte:head>

{#if $tradesLoading && $trades.length === 0}
	<PageHead eyebrow="workspace" title="Trades" meta="loading ledger…" />
	<TableSkeleton rows={6} />
{:else if $tradesError && $trades.length === 0}
	<PageHead eyebrow="workspace" title="Trades" />
	<StateBlock
		kind="error"
		title="Couldn't reach the backend"
		body="{$tradesError} — start the API and retry."
		actionLabel="Retry"
		onAction={() => void loadTrades()}
	/>
{:else if $trades.length === 0 && !$ledgerHasFilter}
	<PageHead eyebrow="workspace" title="Trades" />
	<StateBlock
		title="No trades yet"
		body="Open your first trade here, or log one with the Telegram bot — it appears live."
		actionLabel="Open trade"
		onAction={() => requestOpen()}
	/>
	<TradeModal />
{:else}
	<PageHead
		eyebrow="workspace"
		title="Trades"
		meta="{$tradeCounts.OPEN} open · {$tradesTotal} logged · {$tradeCounts.CLOSED} closed"
	>
		<button type="button" onclick={() => requestOpen()} class="btn btn-primary h-10 px-4 text-sm">
			<Plus size={16} strokeWidth={2.2} aria-hidden="true" />
			Open trade
		</button>
	</PageHead>

	<section
		class="card mb-7 overflow-hidden rise"
		style="animation-delay: 40ms"
		aria-label="Performance at a glance"
	>
		<div class="grid grid-cols-2 gap-px bg-line sm:grid-cols-4">
			{#each ribbon as cell, i (cell.label)}
				<div class="bg-panel px-4 py-3.5">
					<p class="eyebrow">{cell.label}</p>
					<p
						class="display mt-1.5 text-[1.7rem] leading-none tabular-nums {cell.tone} {cell.tone.includes(
							'win'
						)
							? 'text-glow-win'
							: cell.tone.includes('loss')
								? 'text-glow-loss'
								: ''}"
						use:countup={{ value: cell.value, format: cell.format }}
					>
						{cell.format(cell.value)}
					</p>
					<p class="num mt-1.5 text-[10.5px] text-dim">{cell.hint}</p>
				</div>
			{/each}
		</div>
	</section>

	<OpenTrades />
	<TradeTable />
	<TradeModal />
{/if}

{#if $lifecycleModal?.kind === 'open'}
	<TradeOpenModal />
{:else if $lifecycleModal?.kind === 'close'}
	<TradeCloseModal tradeId={$lifecycleModal.tradeId} />
{/if}
