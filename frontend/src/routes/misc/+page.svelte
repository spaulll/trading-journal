<script lang="ts">
	import PageHead from '$lib/components/PageHead.svelte';
	import Mt5ImportCard from '$lib/components/Mt5ImportCard.svelte';
	import RepairUnpricedCard from '$lib/components/RepairUnpricedCard.svelte';
</script>

<svelte:head>
	<title>Misc · Trading Journal</title>
</svelte:head>

<PageHead eyebrow="workspace" title="Misc" meta="Broker import + ledger repair" />

<div class="grid grid-cols-1 gap-4 xl:grid-cols-2">
	<Mt5ImportCard />
	<RepairUnpricedCard />
</div>
