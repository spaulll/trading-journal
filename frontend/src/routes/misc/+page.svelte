<script lang="ts">
	import PageHead from '$lib/components/PageHead.svelte';
	import BrokerClockCard from '$lib/components/BrokerClockCard.svelte';
	import Mt5ImportCard from '$lib/components/Mt5ImportCard.svelte';
	import RepairUnpricedCard from '$lib/components/RepairUnpricedCard.svelte';
</script>

<svelte:head>
	<title>Misc · Trading Journal</title>
</svelte:head>

<PageHead eyebrow="workspace" title="Misc" meta="Broker clock + import + ledger repair" />

<div class="grid grid-cols-1 gap-4 xl:grid-cols-2">
	<BrokerClockCard />
	<Mt5ImportCard />
	<RepairUnpricedCard />
</div>
