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
		success: 'text-win',
		error: 'text-loss',
		info: 'text-accent'
	};
</script>

<div
	class="pointer-events-none fixed right-4 bottom-24 z-[70] flex w-[calc(100vw-2rem)] max-w-sm flex-col gap-2 lg:right-6 lg:bottom-6"
	aria-live="polite"
>
	{#each $toasts as toast (toast.id)}
		{@const Icon = icons[toast.kind]}
		<div
			transition:fly={TOAST_IN}
			role="status"
			class="pointer-events-auto flex items-start gap-2.5 rounded-2xl border border-line bg-panel/95 px-3.5 py-3 shadow-pop backdrop-blur-xl {styles[
				toast.kind
			]}"
		>
			<Icon size={17} strokeWidth={1.8} aria-hidden="true" class="mt-0.5 shrink-0" />
			<p class="flex-1 text-sm leading-relaxed text-fg">{toast.message}</p>
			<button
				type="button"
				onclick={() => toasts.dismiss(toast.id)}
				aria-label="Dismiss"
				class="shrink-0 rounded-md p-0.5 text-dim transition-colors hover:text-fg active:scale-95"
			>
				<X size={14} strokeWidth={1.8} aria-hidden="true" />
			</button>
		</div>
	{/each}
</div>
