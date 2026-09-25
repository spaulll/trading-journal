<script lang="ts">
	import { onMount } from 'svelte';
	import { Moon, RefreshCw, Sun, Wifi, WifiOff } from 'lucide-svelte';
	import { connected, startPolling } from '$lib/stores/connection';
	import { syncFromBot, syncing } from '$lib/stores/trades';
	import { theme, toggleTheme } from '$lib/stores/theme';

	onMount(() => {
		startPolling();
	});
</script>

<header
	class="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-slate-200 bg-white/85 px-4 backdrop-blur-md sm:px-6 dark:border-slate-800 dark:bg-surface-950/85"
>
	<span class="grid h-8 w-8 place-items-center rounded-lg bg-emerald-500 font-mono text-sm font-bold text-white lg:hidden">J</span>

	<div class="ml-auto flex items-center gap-2 sm:gap-3">
		{#if $connected === null}
			<span class="hidden items-center gap-1.5 rounded-full px-2.5 py-1 font-mono text-[11px] text-slate-400 sm:flex">
				<span class="h-1.5 w-1.5 animate-pulse rounded-full bg-slate-400"></span>
				checking…
			</span>
		{:else if $connected}
			<span class="hidden items-center gap-1.5 rounded-full bg-emerald-500/10 px-2.5 py-1 font-mono text-[11px] text-emerald-600 sm:flex dark:text-emerald-400">
				<Wifi size={12} />
				api
			</span>
		{:else}
			<span class="hidden items-center gap-1.5 rounded-full bg-rose-500/10 px-2.5 py-1 font-mono text-[11px] text-rose-600 sm:flex dark:text-rose-400">
				<WifiOff size={12} />
				offline
			</span>
		{/if}

		<button
			type="button"
			onclick={toggleTheme}
			aria-label="Toggle theme"
			class="grid h-9 w-9 place-items-center rounded-lg border border-slate-200 text-slate-500 transition-all duration-150 hover:text-slate-900 active:scale-95 dark:border-slate-700 dark:text-slate-400 dark:hover:text-white"
		>
			{#if $theme === 'dark'}
				<Sun size={17} />
			{:else}
				<Moon size={17} />
			{/if}
		</button>

		<button
			type="button"
			onclick={() => void syncFromBot()}
			disabled={$syncing}
			class="flex h-9 items-center gap-2 rounded-lg bg-emerald-500 px-3.5 text-sm font-medium text-white transition-all duration-150 hover:bg-emerald-600 active:scale-[0.98] disabled:cursor-wait disabled:opacity-70"
		>
			<RefreshCw size={16} class={$syncing ? 'animate-spin' : ''} />
			<span class="hidden sm:inline">{$syncing ? 'Syncing…' : 'Sync from Bot'}</span>
			<span class="sm:hidden">{$syncing ? '…' : 'Sync'}</span>
		</button>
	</div>
</header>
