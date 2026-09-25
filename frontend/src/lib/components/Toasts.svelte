<script lang="ts">
	import { fly } from 'svelte/transition';
	import { CheckCircle2, Info, X, XCircle } from 'lucide-svelte';
	import { toasts, type ToastKind } from '$lib/stores/toast';
	import { TOAST_IN } from '$lib/utils/transitions';

	const icons: Record<ToastKind, typeof CheckCircle2> = {
		success: CheckCircle2,
		error: XCircle,
		info: Info
	};

	const styles: Record<ToastKind, string> = {
		success: 'border-emerald-500/30 text-emerald-600 dark:text-emerald-400',
		error: 'border-rose-500/30 text-rose-600 dark:text-rose-400',
		info: 'border-slate-500/30 text-slate-600 dark:text-slate-300'
	};
</script>

<div
	class="pointer-events-none fixed right-4 bottom-20 z-[70] flex w-[calc(100vw-2rem)] max-w-sm flex-col gap-2 lg:right-6 lg:bottom-6"
	aria-live="polite"
>
	{#each $toasts as toast (toast.id)}
		{@const Icon = icons[toast.kind]}
		<div
			transition:fly={TOAST_IN}
			role="status"
			class="pointer-events-auto flex items-start gap-2.5 rounded-xl border bg-white/95 px-3.5 py-3 shadow-pop backdrop-blur-md dark:bg-surface-900/95 {styles[
				toast.kind
			]}"
		>
			<Icon size={17} strokeWidth={1.8} aria-hidden="true" class="mt-0.5 shrink-0" />
			<p class="flex-1 text-sm leading-relaxed text-slate-700 dark:text-slate-200">{toast.message}</p>
			<button
				type="button"
				onclick={() => toasts.dismiss(toast.id)}
				aria-label="Dismiss"
				class="shrink-0 rounded-md p-0.5 text-slate-400 transition-colors hover:text-slate-700 focus-visible:outline-emerald-500 active:scale-95 dark:hover:text-slate-200"
			>
				<X size={14} strokeWidth={1.8} aria-hidden="true" />
			</button>
		</div>
	{/each}
</div>
