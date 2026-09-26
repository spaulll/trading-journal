<script lang="ts">
	import { AlertTriangle, Inbox } from 'lucide-svelte';

	const {
		kind = 'empty',
		title,
		body,
		actionLabel,
		onAction
	}: {
		kind?: 'empty' | 'error';
		title: string;
		body: string;
		actionLabel?: string;
		onAction?: () => void;
	} = $props();

	const Icon = $derived(kind === 'error' ? AlertTriangle : Inbox);
</script>

<div
	class="card fade-in flex flex-col items-center gap-2.5 border-dashed px-6 py-14 text-center"
>
	<span
		class="grid h-12 w-12 place-items-center rounded-2xl {kind === 'error'
			? 'bg-loss/12 text-loss'
			: 'bg-accent/12 text-accent'}"
		aria-hidden="true"
	>
		<Icon size={21} strokeWidth={1.7} />
	</span>
	<p class="display text-xl text-fg text-balance">{title}</p>
	<p class="max-w-sm text-sm leading-relaxed text-mut">{body}</p>
	{#if actionLabel && onAction}
		<button type="button" onclick={onAction} class="btn btn-primary mt-2 h-10 px-5 text-sm">
			{actionLabel}
		</button>
	{/if}
</div>
