<script lang="ts">
	import { Inbox, AlertTriangle } from 'lucide-svelte';

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
	class="flex flex-col items-center gap-2 rounded-xl border border-dashed border-slate-300 px-6 py-12 text-center dark:border-slate-700"
>
	<span
		class="grid h-11 w-11 place-items-center rounded-full {kind === 'error'
			? 'bg-rose-500/10 text-rose-500'
			: 'bg-slate-500/10 text-slate-400'}"
	>
		<Icon size={20} />
	</span>
	<p class="text-sm font-medium">{title}</p>
	<p class="max-w-sm text-sm text-slate-500 dark:text-slate-400">{body}</p>
	{#if actionLabel && onAction}
		<button
			type="button"
			onclick={onAction}
			class="mt-2 h-9 rounded-lg bg-emerald-500 px-4 text-sm font-medium text-white transition-all duration-150 hover:bg-emerald-600 active:scale-[0.98]"
		>
			{actionLabel}
		</button>
	{/if}
</div>
