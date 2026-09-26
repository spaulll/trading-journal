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
<header class="rise mb-6 flex flex-wrap items-end justify-between gap-4">
	<div class="min-w-0">
		{#if eyebrow}
			<p class="eyebrow mb-2.5 text-accent">{eyebrow}</p>
		{/if}
		<h1 class="display text-[2rem] leading-[1.05] text-fg sm:text-[2.5rem]">{title}</h1>
		{#if meta}
			<p class="num mt-2 text-[12.5px] text-mut">{meta}</p>
		{/if}
	</div>
	{#if children}
		{@render children()}
	{/if}
</header>
