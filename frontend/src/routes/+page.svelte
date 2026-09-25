<script lang="ts">
	import { onMount } from 'svelte';
	import OpenTrades from '$lib/components/OpenTrades.svelte';
	import StateBlock from '$lib/components/StateBlock.svelte';
	import TableSkeleton from '$lib/components/TableSkeleton.svelte';
	import TradeModal from '$lib/components/TradeModal.svelte';
	import TradeTable from '$lib/components/TradeTable.svelte';
	import { loadTrades, syncFromBot, trades, tradesError, tradesLoading } from '$lib/stores/trades';

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
		body="Log trades with the Telegram bot, then pull them in with a single click."
		actionLabel="Sync from Bot"
		onAction={() => void syncFromBot()}
	/>
	<TradeModal />
{:else}
	<OpenTrades />
	<TradeTable />
	<TradeModal />
{/if}
