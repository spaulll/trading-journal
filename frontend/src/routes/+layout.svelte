<script lang="ts">
	import { onMount } from 'svelte';
	import Sidebar from '$lib/components/Sidebar.svelte';
	import TopBar from '$lib/components/TopBar.svelte';
	import Nav from '$lib/components/Nav.svelte';
	import Toasts from '$lib/components/Toasts.svelte';
	import { startPolling } from '$lib/stores/connection';
	import '../app.css';

	let { children } = $props();

	onMount(() => {
		startPolling();
	});
</script>

<div class="relative z-[1] min-h-[100dvh] bg-base text-fg">
	<a href="#main-content" class="skip-link">Skip to content</a>
	<Sidebar />
	<div class="lg:pl-60">
		<TopBar />
		<main
			id="main-content"
			class="mx-auto w-full max-w-[1560px] scroll-mt-20 px-4 pt-6 pb-28 outline-none sm:px-6 lg:px-8 lg:pt-8 lg:pb-16"
		>
			{@render children()}
		</main>
	</div>
	<Nav />
	<Toasts />
</div>
