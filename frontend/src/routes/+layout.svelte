<script lang="ts">
	import Header from '$lib/components/Header.svelte';
	import Nav from '$lib/components/Nav.svelte';
	import Toasts from '$lib/components/Toasts.svelte';
	import '../app.css';

	let { children } = $props();
</script>

<div class="relative z-[1] min-h-[100dvh] bg-surface-50 text-slate-900 dark:bg-surface-950 dark:text-slate-100">
	<a href="#main-content" class="skip-link">Skip to content</a>
	<Nav />
	<div class="lg:pl-60">
		<Header />
		<main id="main-content" class="mx-auto w-full max-w-7xl scroll-mt-20 px-4 pt-6 pb-28 outline-none sm:px-6 lg:pb-12">
			{@render children()}
		</main>
	</div>
	<Toasts />
</div>
