<script lang="ts">
	import { AlertTriangle, Inbox } from 'lucide-svelte';

	const {
		kind = 'empty',
		title,
		body,
		actionLabel,
		onAction,
		actionTone = 'primary',
		secondary = []
	}: {
		kind?: 'empty' | 'error';
		title: string;
		body: string;
		actionLabel?: string;
		onAction?: () => void;
		/** `ghost` keeps the page's own primary action the only brass accent. */
		actionTone?: 'primary' | 'ghost';
		/** At most two quiet shortcuts beside the starter action. */
		secondary?: Array<{ label: string; onAction: () => void }>;
	} = $props();

	const Icon = $derived(kind === 'error' ? AlertTriangle : Inbox);
	const shortcuts = $derived(secondary.slice(0, 2));
</script>

<div class="card fade-in flex flex-col items-center gap-2 border-dashed px-6 py-10 text-center">
	<span
		class="grid h-10 w-10 place-items-center rounded-xl {kind === 'error'
			? 'bg-loss/12 text-loss'
			: 'bg-accent/12 text-accent'}"
		aria-hidden="true"
	>
		<Icon size={18} strokeWidth={1.7} />
	</span>
	<p class="mt-0.5 text-lg font-sans text-fg text-balance">{title}</p>
	<p class="max-w-sm text-sm leading-relaxed text-pretty text-mut">{body}</p>
	{#if (actionLabel && onAction) || shortcuts.length > 0}
		<div class="mt-2 flex flex-wrap items-center justify-center gap-2">
			{#if actionLabel && onAction}
				<button
					type="button"
					onclick={onAction}
					class="btn h-9 px-4 text-[13px] {actionTone === 'primary' ? 'btn-primary' : 'btn-ghost'}"
				>
					{actionLabel}
				</button>
			{/if}
			{#each shortcuts as shortcut (shortcut.label)}
				<button type="button" onclick={shortcut.onAction} class="btn btn-ghost h-9 px-3.5 text-[13px]">
					{shortcut.label}
				</button>
			{/each}
		</div>
	{/if}
</div>
