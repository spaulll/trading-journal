<script lang="ts">
	const { rows = 5 }: { rows?: number } = $props();
</script>

<div class="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-800" aria-hidden="true">
	{#each Array(rows) as _, i}
		<div
			class="h-12 animate-pulse border-b border-slate-100 bg-gradient-to-r from-slate-100 via-slate-50 to-slate-100 last:border-0 dark:border-slate-800/60 dark:from-surface-900 dark:via-surface-800 dark:to-surface-900"
			style="animation-delay: {i * 90}ms"
		></div>
	{/each}
</div>
