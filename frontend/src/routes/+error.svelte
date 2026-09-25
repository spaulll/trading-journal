<script lang="ts">
	import { page } from '$app/state';

	const status = $derived(page.status);
	const is404 = $derived(status === 404);
</script>

<svelte:head>
	<title>{status} · Trading Journal</title>
	<meta name="description" content="Trading Journal error page" />
</svelte:head>

<div
	class="flex flex-col items-center gap-2 rounded-xl border border-dashed border-slate-300 bg-white/60 px-6 py-12 text-center shadow-card dark:border-white/10 dark:bg-surface-900/60"
>
	<span
		class="grid h-11 w-11 place-items-center rounded-xl bg-emerald-500/10 font-mono text-sm font-bold text-emerald-600 dark:text-emerald-400"
		aria-hidden="true"
	>
		{status}
	</span>
	<p class="text-sm font-semibold tracking-tight text-balance">
		{is404 ? 'Page not found' : 'Something went wrong'}
	</p>
	<p class="max-w-sm text-sm leading-relaxed text-slate-500 dark:text-slate-400">
		{is404
			? 'This view does not exist. Check the URL or head back to your trades.'
			: 'The app hit an unexpected error. Go back and try again.'}
	</p>
	<a
		href="/"
		class="mt-2 inline-flex h-9 items-center rounded-lg bg-emerald-500 px-4 text-sm font-semibold text-white shadow-lift transition-all duration-150 hover:bg-emerald-600 focus-visible:outline-emerald-500 active:scale-[0.98]"
	>
		Back to trades
	</a>
</div>
