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
	class="rise mx-auto flex max-w-md flex-col items-center gap-3 rounded-2xl border border-line bg-panel px-6 py-14 text-center shadow-card"
>
	<span
		class="display grid h-14 w-14 place-items-center rounded-2xl border border-accent/30 bg-accent/10 text-xl text-accent"
		aria-hidden="true"
	>
		{status}
	</span>
	<p class="display mt-1 text-2xl text-fg">
		{is404 ? 'Page not found' : 'Something went wrong'}
	</p>
	<p class="max-w-sm text-sm leading-relaxed text-mut">
		{is404
			? 'This view does not exist. Check the URL or head back to your trades.'
			: 'The app hit an unexpected error. Go back and try again.'}
	</p>
	<a href="/" class="btn-primary mt-3 h-10 px-5 text-sm">Back to trades</a>
</div>
