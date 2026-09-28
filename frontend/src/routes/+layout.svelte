<script lang="ts">
	import { onMount } from 'svelte';
	import Sidebar from '$lib/components/Sidebar.svelte';
	import TopBar from '$lib/components/TopBar.svelte';
	import Nav from '$lib/components/Nav.svelte';
	import Toasts from '$lib/components/Toasts.svelte';
	import OfflineBanner from '$lib/components/OfflineBanner.svelte';
	import { startPolling } from '$lib/stores/connection';
	import { loadBrokerOffset } from '$lib/stores/broker';
	import { sidebarCollapsed } from '$lib/stores/ui';
	import '../app.css';

	let { children } = $props();

	onMount(() => {
		startPolling();
		void loadBrokerOffset();
		// PWA shell: cache app HTML/CSS/JS so the journal opens during
		// outages. Data snapshots are separate (see $lib/offline-snapshot).
		try {
			if ('serviceWorker' in navigator && window.isSecureContext !== false) {
				void navigator.serviceWorker.register('/sw.js').catch(() => undefined);
			}
		} catch {
			/* offline shell unavailable — pages still work online */
		}
	});
</script>

<div class="relative z-[1] min-h-[100dvh] bg-base text-fg">
	<a href="#main-content" class="skip-link">Skip to content</a>
	<Sidebar />
	<div class="transition-[padding] duration-300 ease-spring {$sidebarCollapsed ? 'lg:pl-[68px]' : 'lg:pl-60'}">
		<TopBar />
		<OfflineBanner />
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
