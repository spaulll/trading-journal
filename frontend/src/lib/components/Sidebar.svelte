<script lang="ts">
	import { page } from '$app/state';
	import { Moon, RefreshCw, Sun } from 'lucide-svelte';
	import Logo from './Logo.svelte';
	import { NAV_LINKS, isActiveLink } from '$lib/nav';
	import { checkConnection, connected } from '$lib/stores/connection';
	import { refreshTrades, syncing } from '$lib/stores/trades';
	import { theme, toggleTheme } from '$lib/stores/theme';

	const statusLabel = $derived(
		$connected === null ? 'checking' : $connected ? 'live' : 'offline'
	);
</script>

<!-- Desktop: fixed brass-edged rail. Mobile uses TopBar + bottom tab bar. -->
<aside
	class="fixed inset-y-0 left-0 z-40 hidden w-60 flex-col border-r border-line bg-panel/85 backdrop-blur-xl lg:flex"
	aria-label="Workspace"
>
	<a href="/" class="flex items-center gap-3 px-5 pt-5 pb-6">
		<Logo size={36} />
		<span class="flex min-w-0 flex-col leading-none">
			<span class="display truncate text-[19px] leading-none text-fg">Trading Journal</span>
			<span class="eyebrow mt-1.5">self-hosted</span>
		</span>
	</a>

	<nav aria-label="Primary" class="flex flex-col gap-1 px-3">
		{#each NAV_LINKS as link, i (link.href)}
			{@const Icon = link.icon}
			{@const isActive = isActiveLink(link.href, page.url.pathname)}
			<a
				href={link.href}
				aria-current={isActive ? 'page' : undefined}
				class="group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition-all duration-300 ease-spring {isActive
					? 'bg-raised text-fg shadow-[inset_0_1px_0_rgb(255_255_255/0.05)]'
					: 'text-mut hover:bg-raised/60 hover:text-fg'}"
				style="animation: rise 0.5s cubic-bezier(0.22, 1, 0.36, 1) {i * 70}ms both;"
			>
				<span
					class="absolute top-1/2 left-0 h-5 w-[3px] -translate-y-1/2 rounded-full bg-accent transition-all duration-300 ease-spring {isActive
						? 'opacity-100'
						: 'opacity-0'}"
					aria-hidden="true"
				></span>
				<Icon
					size={17}
					strokeWidth={isActive ? 2 : 1.6}
					class="transition-colors duration-200 {isActive ? 'text-accent' : ''}"
					aria-hidden="true"
				/>
				<span class="font-medium tracking-[-0.01em]">{link.label}</span>
			</a>
		{/each}
	</nav>

	<div class="mt-auto flex flex-col gap-2.5 px-3 pb-4">
		<div
			class="flex items-center gap-2 rounded-xl border border-line bg-raised/60 px-3 py-2"
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
			<span class="eyebrow">{statusLabel}</span>
			<span class="eyebrow ml-auto opacity-60">api</span>
		</div>

		<button
			type="button"
			onclick={() => {
				void refreshTrades();
				void checkConnection();
			}}
			disabled={$syncing}
			title="Reload trades from the API"
			class="btn btn-primary h-10 w-full text-[13px]"
		>
			<RefreshCw
				size={15}
				strokeWidth={2}
				aria-hidden="true"
				class={$syncing ? 'animate-spin' : ''}
			/>
			{$syncing ? 'Refreshing' : 'Refresh data'}
		</button>

		<button
			type="button"
			onclick={toggleTheme}
			title="Toggle light / dark"
			class="btn btn-ghost h-9 w-full text-[13px]"
		>
			{#if $theme === 'dark'}
				<Sun size={15} strokeWidth={1.8} aria-hidden="true" />
				<span>Light mode</span>
			{:else}
				<Moon size={15} strokeWidth={1.8} aria-hidden="true" />
				<span>Dark mode</span>
			{/if}
		</button>

		<p class="eyebrow pt-1 text-center opacity-70">v2 · local</p>
	</div>
</aside>
