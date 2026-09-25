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
	class="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-slate-200 bg-white/85 px-4 shadow-card backdrop-blur-md sm:px-6 dark:border-white/[0.07] dark:bg-surface-950/85"
>
	<span class="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-emerald-500 font-mono text-sm font-bold text-white lg:hidden" aria-hidden="true">J</span>

	<div class="ml-auto flex items-center gap-2 sm:gap-3">
		{#if $connected === null}
			<span class="hidden items-center gap-1.5 rounded-full px-2.5 py-1 font-mono text-[11px] tabular-nums text-slate-400 sm:flex">
				<span class="h-1.5 w-1.5 animate-pulse rounded-full bg-slate-400" aria-hidden="true"></span>
				checking…
			</span>
		{:else if $connected}
			<span class="hidden items-center gap-1.5 rounded-full bg-emerald-500/10 px-2.5 py-1 font-mono text-[11px] tabular-nums text-emerald-600 sm:flex dark:text-emerald-400">
				<Wifi size={12} strokeWidth={1.8} aria-hidden="true" />
				api
			</span>
		{:else}
			<span class="hidden items-center gap-1.5 rounded-full bg-rose-500/10 px-2.5 py-1 font-mono text-[11px] tabular-nums text-rose-600 sm:flex dark:text-rose-400">
				<WifiOff size={12} strokeWidth={1.8} aria-hidden="true" />
				offline
			</span>
		{/if}

		<button
			type="button"
			onclick={toggleTheme}
			aria-label="Toggle theme"
			title="Toggle light / dark"
			class="grid h-9 w-9 place-items-center rounded-lg border border-slate-200 text-slate-500 transition-all duration-150 hover:border-slate-300 hover:text-slate-900 focus-visible:outline-emerald-500 active:scale-95 dark:border-white/10 dark:text-slate-400 dark:hover:border-white/20 dark:hover:text-white"
		>
			{#if $theme === 'dark'}
				<Sun size={17} strokeWidth={1.8} aria-hidden="true" />
			{:else}
				<Moon size={17} strokeWidth={1.8} aria-hidden="true" />
			{/if}
		</button>

		<button
			type="button"
			onclick={() => void syncFromBot()}
			disabled={$syncing}
			class="flex h-9 items-center gap-2 rounded-lg bg-emerald-500 px-3.5 text-sm font-semibold text-white shadow-lift transition-all duration-150 hover:bg-emerald-600 focus-visible:outline-emerald-500 active:scale-[0.98] disabled:cursor-wait disabled:opacity-70"
		>
			<RefreshCw size={16} strokeWidth={1.8} aria-hidden="true" class={$syncing ? 'animate-spin' : ''} />
			<span class="hidden sm:inline">{$syncing ? 'Syncing…' : 'Sync from Bot'}</span>
			<span class="sm:hidden">{$syncing ? '…' : 'Sync'}</span>
		</button>
	</div>
</header>
