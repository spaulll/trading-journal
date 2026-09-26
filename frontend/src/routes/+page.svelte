<script lang="ts">
	import { onMount } from 'svelte';
	import { Plus } from 'lucide-svelte';
	import OpenTrades from '$lib/components/OpenTrades.svelte';
	import PageHead from '$lib/components/PageHead.svelte';
	import StateBlock from '$lib/components/StateBlock.svelte';
	import TableSkeleton from '$lib/components/TableSkeleton.svelte';
	import TradeCloseModal from '$lib/components/TradeCloseModal.svelte';
	import TradeModal from '$lib/components/TradeModal.svelte';
	import TradeOpenModal from '$lib/components/TradeOpenModal.svelte';
	import TradeTable from '$lib/components/TradeTable.svelte';
	import {
		lifecycleModal,
		loadTrades,
		openTrades,
		requestOpen,
		trades,
		tradesError,
		tradesLoading
	} from '$lib/stores/trades';
	import { fmtMoney, fmtR, pnlTone, toneText } from '$lib/utils/format';
	import { countup } from '$lib/utils/motion';

	onMount(() => {
		void loadTrades();
	});

	const closed = $derived($trades.filter((t) => t.status !== 'OPEN'));

	/** Client-side roll-up for the masthead ribbon — no extra API call. */
	const stats = $derived.by(() => {
		const wins = closed.filter((t) => (t.net_pnl ?? 0) > 0).length;
		const losses = closed.filter((t) => (t.net_pnl ?? 0) < 0).length;
		const net = closed.reduce((s, t) => s + (t.net_pnl ?? 0), 0);
		const rs = closed
			.map((t) => t.r_multiple)
			.filter((v): v is number => v !== null && v !== undefined);
		const avgR = rs.length ? rs.reduce((a, b) => a + b, 0) / rs.length : null;
		const wr = wins + losses > 0 ? (wins / (wins + losses)) * 100 : null;
		return { net, wr, avgR, closed: closed.length, wins, losses };
	});

	const ribbon = $derived([
		{
			label: 'Net realized',
			value: stats.net,
			format: (v: number) => fmtMoney(v),
			tone: toneText[pnlTone(stats.net)],
			hint: `${stats.closed} closed`
		},
		{
			label: 'Win rate',
			value: stats.wr ?? 0,
			format: (v: number) => `${v.toFixed(1)}%`,
			tone: 'text-fg',
			hint: `${stats.wins}W · ${stats.losses}L`
		},
		{
			label: 'Average R',
			value: stats.avgR ?? 0,
			format: (v: number) => fmtR(v),
			tone: toneText[pnlTone(stats.avgR)],
			hint: stats.avgR === null ? 'no R data' : 'per closed trade'
		},
		{
			label: 'Open now',
			value: $openTrades.length,
			format: (v: number) => `${Math.round(v)}`,
			tone: $openTrades.length > 0 ? 'text-accent' : 'text-dim',
			hint: 'live positions'
		}
	]);
</script>

<svelte:head>
	<title>Trades · Trading Journal</title>
</svelte:head>

{#if $tradesLoading}
	<PageHead eyebrow="workspace" title="Trades" meta="loading ledger…" />
	<TableSkeleton rows={6} />
{:else if $tradesError}
	<PageHead eyebrow="workspace" title="Trades" />
	<StateBlock
		kind="error"
		title="Couldn't reach the backend"
		body="{$tradesError} — start the API and retry."
		actionLabel="Retry"
		onAction={() => void loadTrades()}
	/>
{:else if $trades.length === 0}
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
		meta="{$openTrades.length} open · {$trades.length} logged · {closed.length} closed"
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
