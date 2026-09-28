<script lang="ts">
	import { page } from '$app/state';
	import { Moon, PanelLeftClose, PanelLeftOpen, RefreshCw, Sun } from 'lucide-svelte';
	import Logo from './Logo.svelte';
	import { NAV_LINKS, isActiveLink } from '$lib/nav';
	import { checkConnection, connected } from '$lib/stores/connection';
	import { refreshTrades, syncing } from '$lib/stores/trades';
	import { theme, toggleTheme } from '$lib/stores/theme';
	import { sidebarCollapsed, toggleSidebar } from '$lib/stores/ui';

	const statusLabel = $derived(
		$connected === null ? 'checking' : $connected ? 'live' : 'offline'
	);
</script>

<!-- Desktop: fixed brass-edged rail. Mobile uses TopBar + bottom tab bar. -->
<aside
	class="fixed inset-y-0 left-0 z-40 hidden flex-col border-r border-line bg-panel/85 backdrop-blur-xl transition-[width] duration-300 ease-spring lg:flex {$sidebarCollapsed
		? 'w-[68px]'
		: 'w-60'}"
	aria-label="Workspace"
>
	<button
		type="button"
		onclick={toggleSidebar}
		aria-expanded={!$sidebarCollapsed}
		aria-label={$sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
		title={$sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
		class="absolute top-6 -right-3 z-50 grid h-6 w-6 place-items-center rounded-full border border-line bg-raised text-dim shadow-pop transition-colors hover:border-edge hover:text-fg"
	>
		{#if $sidebarCollapsed}
			<PanelLeftOpen size={13} strokeWidth={2} aria-hidden="true" />
		{:else}
			<PanelLeftClose size={13} strokeWidth={2} aria-hidden="true" />
		{/if}
	</button>

	<a href="/" class="flex items-center gap-3 px-5 pt-5 pb-6 {$sidebarCollapsed ? 'justify-center px-0' : ''}" title="Trading Journal">
		<Logo size={36} />
		{#if !$sidebarCollapsed}
			<span class="flex min-w-0 flex-col leading-none">
				<span class="display truncate text-[19px] leading-none text-fg">Trading Journal</span>
				<span class="eyebrow mt-1.5">self-hosted</span>
			</span>
		{/if}
	</a>

	<nav aria-label="Primary" class="flex flex-col gap-1 px-3">
		{#each NAV_LINKS as link, i (link.href)}
			{@const Icon = link.icon}
			{@const isActive = isActiveLink(link.href, page.url.pathname)}
			<a
				href={link.href}
				aria-current={isActive ? 'page' : undefined}
				title={link.label}
				class="group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition-all duration-300 ease-spring {$sidebarCollapsed
					? 'justify-center'
					: ''} {isActive
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
				{#if !$sidebarCollapsed}
					<span class="font-medium tracking-[-0.01em]">{link.label}</span>
				{/if}
			</a>
		{/each}
	</nav>

	<div class="mt-auto flex flex-col gap-2.5 px-3 pb-4">
		<div
			class="flex items-center gap-2 rounded-xl border border-line bg-raised/60 px-3 py-2 {$sidebarCollapsed
				? 'justify-center px-0'
				: ''}"
			title={$connected === null
				? 'Checking API'
				: $connected
					? 'API reachable'
					: 'API unreachable'}
		>
			<span
				class="h-1.5 w-1.5 shrink-0 rounded-full {$connected === null
					? 'animate-pulse bg-dim'
					: $connected
						? 'bg-win dot-live'
						: 'bg-loss'}"
				aria-hidden="true"
			></span>
			{#if !$sidebarCollapsed}
				<span class="eyebrow">{statusLabel}</span>
				<span class="eyebrow ml-auto opacity-60">api</span>
			{/if}
		</div>

		<button
			type="button"
			onclick={() => {
				void refreshTrades();
				void checkConnection();
			}}
			disabled={$syncing}
			title="Reload trades from the API"
			class="btn btn-primary h-10 w-full justify-center text-[13px]"
		>
			<RefreshCw
				size={15}
				strokeWidth={2}
				aria-hidden="true"
				class={$syncing ? 'animate-spin' : ''}
			/>
			{#if !$sidebarCollapsed}
				{$syncing ? 'Refreshing' : 'Refresh data'}
			{/if}
		</button>

		<button
			type="button"
			onclick={toggleTheme}
			title="Toggle light / dark"
			class="btn btn-ghost h-9 w-full justify-center text-[13px]"
		>
			{#if $theme === 'dark'}
				<Sun size={15} strokeWidth={1.8} aria-hidden="true" />
				{#if !$sidebarCollapsed}<span>Light mode</span>{/if}
			{:else}
				<Moon size={15} strokeWidth={1.8} aria-hidden="true" />
				{#if !$sidebarCollapsed}<span>Dark mode</span>{/if}
			{/if}
		</button>

		{#if !$sidebarCollapsed}
			<p class="eyebrow pt-1 text-center opacity-70">v2 · local</p>
		{/if}
	</div>
</aside>
