<script lang="ts">
	import { onMount } from 'svelte';
	import { tick } from 'svelte';

	export interface SegOption {
		value: string;
		label: string;
		count?: number | string;
		title?: string;
	}

	const {
		options,
		value,
		onChange,
		label,
		mode = 'toggle',
		size = 'md'
	}: {
		options: SegOption[];
		value: string;
		onChange: (v: string) => void;
		label: string;
		mode?: 'tabs' | 'toggle';
		size?: 'sm' | 'md';
	} = $props();

	let container: HTMLDivElement | null = $state(null);
	let pill = $state({ x: 0, w: 0, ready: false });

	const btnClass = $derived(
		size === 'sm'
			? 'chip px-3 py-1 font-mono text-xs tabular-nums'
			: 'chip px-3.5 py-1.5 text-[13px] font-semibold'
	);

	function measure(): void {
		const c = container;
		if (!c) return;
		const btns = c.querySelectorAll<HTMLButtonElement>('[data-seg-btn]');
		const el = btns[options.findIndex((o) => o.value === value)];
		if (!el) {
			pill.ready = false;
			return;
		}
		const cr = c.getBoundingClientRect();
		const r = el.getBoundingClientRect();
		pill = { x: r.left - cr.left, w: r.width, ready: true };
	}

	onMount(() => {
		void tick().then(measure);
		if (document.fonts) void document.fonts.ready.then(() => measure());
		const ro = new ResizeObserver(() => measure());
		if (container) ro.observe(container);
		window.addEventListener('resize', measure);
		return () => {
			ro.disconnect();
			window.removeEventListener('resize', measure);
		};
	});

	$effect(() => {
		void value;
		void options.length;
		void tick().then(measure);
	});
</script>

<div
	bind:this={container}
	role={mode === 'tabs' ? 'tablist' : 'group'}
	aria-label={label}
	class="relative flex rounded-xl border border-line bg-raised/50 p-1"
>
	<span
		aria-hidden="true"
		class="seg-pill pointer-events-none absolute top-1 bottom-1 left-0 rounded-lg"
		style="transform: translateX({pill.x}px); width: {pill.w}px; opacity: {pill.ready ? 1 : 0};"
	></span>
	{#each options as o (o.value)}
		<button
			type="button"
			data-seg-btn
			role={mode === 'tabs' ? 'tab' : undefined}
			aria-selected={mode === 'tabs' ? value === o.value : undefined}
			aria-pressed={mode === 'toggle' ? value === o.value : undefined}
			title={o.title}
			onclick={() => value !== o.value && onChange(o.value)}
			class="relative z-10 flex-1 whitespace-nowrap {btnClass}"
			data-active={value === o.value}
		>
			{o.label}
			{#if o.count !== undefined}
				<span class="ml-1 opacity-60 tabular-nums">{o.count}</span>
			{/if}
		</button>
	{/each}
</div>
