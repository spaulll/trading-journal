<script lang="ts">
	import type { Snippet } from 'svelte';

	const {
		title,
		meta = '',
		delay = 0,
		children
	}: {
		title: string;
		meta?: string;
		delay?: number;
		children: Snippet;
	} = $props();
</script>

<!-- One surface per analytics section: a title, a hairline, then the blocks. -->
<section
	class="card rise min-w-0 p-5"
	style="animation-delay: {delay}ms"
	aria-label={title}
>
	<header class="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-line pb-3">
		<h2 class="font-mono text-xs font-semibold tracking-[0.18em] uppercase text-mut">
			{title}
		</h2>
		{#if meta}
			<p class="num text-[11px] text-dim">{meta}</p>
		{/if}
	</header>
	<div class="min-w-0 pt-4">
		{@render children()}
	</div>
</section>
