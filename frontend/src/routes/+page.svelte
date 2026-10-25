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

	const netTone = $derived(pnlTone(summary?.net_pnl ?? 0));
	const netToneClass = $derived(toneText[netTone]);
	const closed = $derived(summary?.total_trades ?? 0);
	const wins = $derived(summary?.wins ?? 0);
	const losses = $derived(summary?.losses ?? 0);
	const breakeven = $derived(summary?.breakeven ?? 0);
	const unpriced = $derived(summary?.unpriced ?? 0);
	const outcomeLabel = $derived(
		`Outcome mix: ${wins} wins, ${losses} losses, ${breakeven} breakeven${unpriced ? `, ${unpriced} unpriced` : ''}`
	);

	// Supporting figures stay deliberately small — the net is the only number
	// that gets the large treatment.
	const supporting = $derived([
		{
			label: 'Win rate',
			value: wins + losses > 0 ? (summary?.win_rate ?? 0) : null,
			format: (v: number) => `${v.toFixed(1)}%`,
			hint: `${wins}W · ${losses}L`,
			tone: 'text-fg'
		},
		{
			label: 'Average R',
			value: summary?.avg_r ?? null,
			format: (v: number) => fmtR(v),
			hint: summary?.avg_r == null ? 'no R data' : 'per trade',
			tone: 'text-fg'
		},
		{
			label: 'Open now',
			value: summary?.open_trades ?? 0,
			format: (v: number) => `${Math.round(v)}`,
			hint: 'open trades',
			tone: (summary?.open_trades ?? 0) > 0 ? 'text-accent' : 'text-dim'
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
		class="mb-7 grid gap-3 md:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]"
		aria-label="Performance at a glance"
	>
		<div
			class="card relative overflow-hidden border-accent/20 p-4 rise sm:p-5 md:p-6"
			style="animation-delay: 40ms"
		>
			{#if netTone === 'win'}
				<div class="kpi-glow-win pointer-events-none absolute inset-0" aria-hidden="true"></div>
			{:else if netTone === 'loss'}
				<div class="kpi-glow-loss pointer-events-none absolute inset-0" aria-hidden="true"></div>
			{/if}

			<div class="relative">
				<div class="flex items-start justify-between gap-3">
					<p class="eyebrow inline-flex items-center gap-2">
						<span
							class="size-1.5 rounded-full {netTone === 'win'
								? 'bg-win'
								: netTone === 'loss'
									? 'bg-loss'
									: 'bg-flat'}"
							aria-hidden="true"
						></span>
						Net realized
					</p>
					<span
						class="rounded-full border border-line px-2 py-0.5 font-mono text-[11px] text-dim"
					>
						USD
					</span>
				</div>

				<p
					class="display mt-2.5 text-[2.2rem] leading-none tabular-nums {netToneClass} sm:text-[2.5rem] md:text-[2.6rem] xl:text-[2.8rem]"
					use:countup={{ value: summary?.net_pnl ?? 0, format: (v) => fmtMoney(v) }}
				>
					{fmtMoney(summary?.net_pnl ?? 0)}
				</p>
				<p class="num mt-2 text-xs text-mut">
					{closed} closed{unpriced > 0 ? ` · ${unpriced} unpriced` : ''}
				</p>

				<div class="mt-4">
					<div
						class="flex h-1.5 items-stretch gap-1 overflow-hidden rounded-full bg-raised"
						role="img"
						aria-label={outcomeLabel}
					>
						{#if wins > 0}
							<span class="h-full rounded-full bg-win" style={`flex: ${wins} 1 0%`}></span>
						{/if}
						{#if losses > 0}
							<span class="h-full rounded-full bg-loss" style={`flex: ${losses} 1 0%`}></span>
						{/if}
						{#if breakeven > 0}
							<span class="h-full rounded-full bg-flat" style={`flex: ${breakeven} 1 0%`}></span>
						{/if}
					</div>
					<div class="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-dim">
						<span class="inline-flex items-center gap-1.5">
							<span class="size-1.5 rounded-full bg-win" aria-hidden="true"></span>
							Win
						</span>
						<span class="inline-flex items-center gap-1.5">
							<span class="size-1.5 rounded-full bg-loss" aria-hidden="true"></span>
							Loss
						</span>
						<span class="inline-flex items-center gap-1.5">
							<span class="size-1.5 rounded-full bg-flat" aria-hidden="true"></span>
							BE
						</span>
					</div>
				</div>
			</div>
		</div>

		<div class="card overflow-hidden rise" style="animation-delay: 120ms">
			<dl
				class="grid grid-cols-3 divide-x divide-line md:grid-cols-1 md:divide-x-0 md:divide-y md:pt-2"
			>
				{#each supporting as cell (cell.label)}
					<div
						class="min-w-0 px-3 py-3.5 sm:px-4 md:flex md:items-baseline md:justify-between md:gap-4 md:px-5 md:py-2.5"
					>
						<dt class="eyebrow">{cell.label}</dt>
						<dd class="mt-1 min-w-0 md:mt-0 md:text-right">
							{#if cell.value === null}
								<span class="num text-xl leading-none font-medium text-dim">—</span>
							{:else}
								<span
									class="num text-xl leading-none font-medium tracking-[-0.01em] {cell.tone}"
									use:countup={{ value: cell.value, format: cell.format }}
								>
									{cell.format(cell.value)}
								</span>
							{/if}
							<span class="num mt-0.5 block text-[11px] leading-tight text-dim md:mt-1">
								{cell.hint}
							</span>
						</dd>
					</div>
				{/each}
			</dl>
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
