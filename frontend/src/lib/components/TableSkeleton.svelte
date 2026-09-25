<script lang="ts">
	const { rows = 5 }: { rows?: number } = $props();
</script>

<div class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-card dark:border-white/[0.07] dark:bg-surface-900" aria-hidden="true">
	{#each Array(rows) as _, i}
		<div
			class="h-12 animate-pulse border-b border-slate-100 bg-gradient-to-r from-slate-100 via-slate-50 to-slate-100 last:border-0 dark:border-white/[0.05] dark:from-surface-900 dark:via-white/[0.04] dark:to-surface-900"
			style="animation-delay: {i * 90}ms"
		></div>
	{/each}
</div>
