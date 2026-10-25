<script lang="ts">
	let {
		eyebrow,
		title,
		meta,
		children
	}: {
		eyebrow?: string;
		title: string;
		meta?: string;
		children?: import('svelte').Snippet;
	} = $props();
</script>

<!-- Shared page masthead: serif display title, mono meta line, slot for actions. -->
<header class="rise mb-6">
	<div class="flex flex-wrap items-end justify-between gap-x-4 gap-y-3">
		<div class="min-w-0">
			{#if eyebrow}
				<p class="eyebrow mb-2 text-accent">{eyebrow}</p>
			{/if}
			<h1 class="display text-display text-fg">{title}</h1>
		</div>
		{#if children}
			<div class="flex shrink-0 flex-wrap items-center gap-2" data-pagehead-actions>
				{@render children()}
			</div>
		{/if}
	</div>
	{#if meta}
		<p class="num mt-2 text-sm text-mut">{meta}</p>
	{/if}
</header>
