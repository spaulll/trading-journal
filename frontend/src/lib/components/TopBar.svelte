<script lang="ts">
	import { Moon, RefreshCw, Sun } from 'lucide-svelte';
	import Logo from './Logo.svelte';
	import { checkConnection, connected } from '$lib/stores/connection';
	import { refreshTrades, syncing } from '$lib/stores/trades';
	import { theme, toggleTheme } from '$lib/stores/theme';
</script>

<!-- Tablet / phone chrome. Desktop navigation lives in the Sidebar rail. -->
<header
	class="sticky top-0 z-40 border-b border-line bg-base/85 backdrop-blur-xl lg:hidden"
>
	<div class="flex h-14 w-full items-center gap-3 px-4">
		<a href="/" class="flex min-w-0 items-center gap-2.5">
			<Logo size={30} />
			<span class="display truncate text-[17px] leading-none text-fg">Trading Journal</span>
		</a>

		<div class="ml-auto flex items-center gap-2">
			<span
				class="inline-flex h-8 items-center gap-1.5 rounded-full border border-line bg-raised/70 px-2.5"
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
				<span class="eyebrow">{$connected === null ? 'check' : $connected ? 'live' : 'off'}</span>
			</span>

			<button
				type="button"
				onclick={toggleTheme}
				aria-label="Toggle theme"
				title="Toggle light / dark"
				class="btn-icon h-9 w-9"
			>
				{#if $theme === 'dark'}
					<Sun size={16} strokeWidth={1.8} aria-hidden="true" />
				{:else}
					<Moon size={16} strokeWidth={1.8} aria-hidden="true" />
				{/if}
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
				class="btn btn-primary h-9 w-9"
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
