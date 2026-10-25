<script lang="ts">
	import { Moon, RefreshCw, Sun } from 'lucide-svelte';
	import Logo from './Logo.svelte';
	import { checkConnection, connected } from '$lib/stores/connection';
	import { refreshTrades, syncing } from '$lib/stores/trades';
	import { theme, toggleTheme } from '$lib/stores/theme';

	const statusLabel = $derived(
		$connected === null ? 'checking' : $connected ? 'live' : 'offline'
	);
</script>

<!-- Tablet / phone chrome. Desktop navigation lives in the Sidebar rail. -->
<header
	class="sticky top-0 z-40 h-14 border-b border-line bg-base/90 backdrop-blur-xl lg:hidden"
>
	<div class="flex h-full w-full items-center gap-3 px-4">
		<a href="/" class="flex min-w-0 items-center gap-2.5" aria-label="Trading Journal home">
			<Logo size={30} />
			<span class="display truncate text-lg leading-none text-fg">Trading Journal</span>
		</a>

		<div class="ml-auto flex shrink-0 items-center gap-1.5">
			<span
				class="inline-flex h-8 items-center gap-1.5 rounded-full border border-line bg-raised/60 px-2.5"
				role="status"
				aria-live="polite"
				aria-label={`API ${statusLabel}`}
				title={$connected === null
					? 'Checking API'
					: $connected
						? 'API reachable'
						: 'API unreachable'}
			>
				<span
					class="h-1.5 w-1.5 rounded-full {$connected === null
						? 'animate-pulse bg-dim'
						: $connected
							? 'bg-win dot-live'
							: 'bg-loss'}"
					aria-hidden="true"
				></span>
				<span class="font-mono text-xs tracking-[0.12em] uppercase">{statusLabel}</span>
			</span>

			<button
				type="button"
				onclick={toggleTheme}
				aria-label={$theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
				title="Toggle light / dark"
				class="btn-icon h-10 w-10"
			>
				{#key $theme}
					<span class="anim-pop inline-flex" style="animation-duration: 0.3s">
						{#if $theme === 'dark'}
							<Sun size={16} strokeWidth={1.8} aria-hidden="true" />
						{:else}
							<Moon size={16} strokeWidth={1.8} aria-hidden="true" />
						{/if}
					</span>
				{/key}
			</button>

			<button
				type="button"
				onclick={() => {
					void refreshTrades();
					void checkConnection();
				}}
				disabled={$syncing}
				aria-label="Refresh trades"
				title="Reload trades and re-check the API"
				class="btn-icon h-10 w-10"
			>
				<RefreshCw
					size={15}
					strokeWidth={2}
					aria-hidden="true"
					class={$syncing ? 'animate-spin' : ''}
				/>
			</button>
		</div>
	</div>
</header>
