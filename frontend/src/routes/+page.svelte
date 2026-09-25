<script lang="ts">
	import { onMount } from 'svelte';
	import { Plus } from 'lucide-svelte';
	import OpenTrades from '$lib/components/OpenTrades.svelte';
	import StateBlock from '$lib/components/StateBlock.svelte';
	import TableSkeleton from '$lib/components/TableSkeleton.svelte';
	import TradeCloseModal from '$lib/components/TradeCloseModal.svelte';
	import TradeModal from '$lib/components/TradeModal.svelte';
	import TradeOpenModal from '$lib/components/TradeOpenModal.svelte';
	import TradeTable from '$lib/components/TradeTable.svelte';
	import {
		lifecycleModal,
		loadTrades,
		requestOpen,
		trades,
		tradesError,
		tradesLoading
	} from '$lib/stores/trades';

	onMount(() => {
		void loadTrades();
	});
</script>

<svelte:head>
	<title>Trades · Trading Journal</title>
</svelte:head>

{#if $tradesLoading}
	<TableSkeleton rows={6} />
{:else if $tradesError}
	<StateBlock
		kind="error"
		title="Couldn't reach the backend"
		body="{$tradesError} — start the API and retry."
		actionLabel="Retry"
		onAction={() => void loadTrades()}
	/>
{:else if $trades.length === 0}
	<StateBlock
		title="No trades yet"
		body="Open your first trade here, or log one with the Telegram bot — it appears live."
		actionLabel="Open trade"
		onAction={() => requestOpen()}
	/>
	<TradeModal />
{:else}
	<div class="mb-4 flex items-center justify-between gap-2">
		<h1 class="text-base font-semibold tracking-tight">Trades</h1>
		<button
			type="button"
			onclick={() => requestOpen()}
			class="flex h-9 items-center gap-1.5 rounded-lg bg-emerald-500 px-3.5 text-sm font-semibold text-white shadow-lift transition-all duration-150 hover:bg-emerald-600 focus-visible:outline-emerald-500 active:scale-[0.98]"
		>
			<Plus size={16} strokeWidth={2.2} aria-hidden="true" />
			Open trade
		</button>
	</div>
	<OpenTrades />
	<TradeTable />
	<TradeModal />
{/if}

{#if $lifecycleModal?.kind === 'open'}
	<TradeOpenModal />
{:else if $lifecycleModal?.kind === 'close'}
	<TradeCloseModal tradeId={$lifecycleModal.tradeId} />
{/if}
