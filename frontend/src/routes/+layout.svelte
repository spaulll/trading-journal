<script lang="ts">
	import Header from '$lib/components/Header.svelte';
	import Nav from '$lib/components/Nav.svelte';
	import Toasts from '$lib/components/Toasts.svelte';
	import '../app.css';

	let { children } = $props();
</script>

<div class="min-h-[100dvh] bg-surface-50 text-slate-900 dark:bg-surface-950 dark:text-slate-100">
	<Nav />
	<div class="lg:pl-60">
		<Header />
		<main class="mx-auto w-full max-w-7xl px-4 pt-6 pb-28 sm:px-6 lg:pb-12">
			{@render children()}
		</main>
	</div>
	<Toasts />
</div>
