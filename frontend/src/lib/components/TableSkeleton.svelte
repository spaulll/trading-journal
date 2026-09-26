<script lang="ts">
	const { rows = 5 }: { rows?: number } = $props();
</script>

<div class="card overflow-hidden" aria-hidden="true">
	{#each Array(rows) as _, i}
		<div
			class="skeleton mx-4 my-3 h-9 rounded-lg last:mb-4"
			style="animation-delay: {i * 90}ms"
		></div>
	{/each}
</div>
