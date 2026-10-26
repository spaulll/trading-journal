<script lang="ts">
	import { page } from '$app/state';
	import { Moon, PanelLeftClose, PanelLeftOpen, RefreshCw, Sun } from 'lucide-svelte';
	import Logo from './Logo.svelte';
	import { NAV_LINKS, isActiveLink } from '$lib/nav';
	import { checkConnection, connected } from '$lib/stores/connection';
	import { refreshTrades, syncing } from '$lib/stores/trades';
	import { theme, toggleTheme } from '$lib/stores/theme';
	import { sidebarCollapsed, toggleSidebar } from '$lib/stores/ui';
	import { STAGGER_DELAY, STAGGER_MAX } from '$lib/utils/motion-timing';

	const statusLabel = $derived(
		$connected === null ? 'checking' : $connected ? 'live' : 'offline'
	);

	const stagger = (i: number) => Math.min(i, STAGGER_MAX - 1) * STAGGER_DELAY;
</script>

<!-- Desktop: fixed brass-edged rail. Mobile uses TopBar + bottom tab bar. -->
<aside
	class="fixed inset-y-0 left-0 z-40 hidden flex-col border-r border-line bg-panel/90 backdrop-blur-xl transition-[width] duration-300 ease-spring lg:flex {$sidebarCollapsed
		? 'w-[68px]'
		: 'w-60'}"
	id="sidebar"
	aria-label="Workspace"
>
	<div class="flex items-center gap-2 px-4 pt-5 pb-5 {$sidebarCollapsed ? 'justify-center px-0' : ''}">
		<a
			href="/"
			class="flex min-w-0 items-center gap-3 transition-opacity duration-200 hover:opacity-90 active:opacity-80"
			title="Trading Journal"
			aria-label="Trading Journal home"
		>
			<Logo size={36} />
			{#if !$sidebarCollapsed}
				<span class="flex min-w-0 flex-col leading-none">
					<span class="display truncate text-lg leading-none text-fg">Trading Journal</span>
					<span class="eyebrow mt-1.5">self-hosted</span>
				</span>
			{/if}
		</a>
		{#if !$sidebarCollapsed}
			<button
				type="button"
				onclick={toggleSidebar}
				aria-expanded="true"
				aria-controls="sidebar"
				aria-label="Collapse sidebar"
				title="Collapse sidebar"
				class="ml-auto grid h-7 w-7 shrink-0 place-items-center rounded-control border border-line bg-raised/60 text-dim transition-[background-color,border-color,color,transform] duration-200 ease-spring hover:border-edge hover:bg-raised hover:text-fg active:scale-95"
			>
				<PanelLeftClose size={14} strokeWidth={2} aria-hidden="true" />
			</button>
		{/if}
	</div>

	<nav aria-label="Primary" class="flex flex-col gap-1 px-3">
		{#if !$sidebarCollapsed}
			<p class="eyebrow px-3 pt-1 pb-1.5">Workspace</p>
		{/if}
		{#each NAV_LINKS as link, i (link.href)}
			{@const Icon = link.icon}
			{@const isActive = isActiveLink(link.href, page.url.pathname)}
			<a
				href={link.href}
				aria-current={isActive ? 'page' : undefined}
				aria-label={link.label}
				title={link.label}
				class="rise group relative flex items-center gap-3 rounded-control border px-3 py-2.5 text-sm transition-[background-color,border-color,color,box-shadow] duration-200 ease-spring {$sidebarCollapsed
					? 'justify-center'
					: ''} {isActive
					? 'border-line bg-raised text-fg shadow-inset-highlight active:bg-raised'
					: 'border-transparent text-mut hover:bg-raised/50 hover:text-fg active:bg-raised/70'}"
				style="animation-delay: {stagger(i)}ms;"
			>
				<span
					class="absolute top-1/2 left-0 h-4 w-[2px] -translate-y-1/2 rounded-full bg-accent transition-opacity duration-200 {isActive
						? 'opacity-100'
						: 'opacity-0'}"
					aria-hidden="true"
				></span>
				<Icon
					size={17}
					strokeWidth={isActive ? 2 : 1.6}
					class="shrink-0 transition-transform duration-200 ease-spring {isActive
						? 'text-accent'
						: 'group-hover:translate-x-0.5'}"
					aria-hidden="true"
				/>
				{#if !$sidebarCollapsed}
					<span class="font-medium tracking-[-0.01em]">{link.label}</span>
				{/if}
			</a>
		{/each}
	</nav>

	<div class="mt-auto {$sidebarCollapsed ? 'px-2' : 'px-3'} pb-4">
		<div class="rounded-card border border-line bg-raised/35 {$sidebarCollapsed ? 'p-1.5' : 'p-2'}">
			<div
				class="flex items-center gap-2 {$sidebarCollapsed ? 'justify-center' : 'px-2'} py-1"
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
					<span class="eyebrow ml-auto">api</span>
				{/if}
			</div>

			<div class="mt-1.5 flex flex-col gap-1">
				<button
					type="button"
					onclick={() => {
						void refreshTrades();
						void checkConnection();
					}}
					disabled={$syncing}
					aria-label="Refresh trades"
					title="Reload trades from the API"
					class="btn btn-ghost group h-8 w-full justify-center gap-1.5 {$sidebarCollapsed
						? 'px-0'
						: 'px-2'} text-xs"
				>
					<RefreshCw
						size={14}
						strokeWidth={2}
						aria-hidden="true"
						class="transition-transform duration-200 {$syncing
							? 'animate-spin'
							: 'group-hover:scale-105'}"
					/>
					{#if !$sidebarCollapsed}
						<span>{$syncing ? 'Refreshing' : 'Refresh'}</span>
					{/if}
				</button>

				<button
					type="button"
					onclick={toggleTheme}
					aria-label={$theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
					title="Toggle light / dark"
					class="btn btn-ghost group h-8 w-full justify-center gap-1.5 {$sidebarCollapsed
						? 'px-0'
						: 'px-2'} text-xs"
				>
					{#key $theme}
						<span
							class="anim-pop inline-flex transition-transform duration-200 group-hover:scale-105"
							style="animation-duration: 0.3s"
						>
							{#if $theme === 'dark'}
								<Sun size={14} strokeWidth={1.8} aria-hidden="true" />
							{:else}
								<Moon size={14} strokeWidth={1.8} aria-hidden="true" />
							{/if}
						</span>
					{/key}
					{#if !$sidebarCollapsed}
						<span>{$theme === 'dark' ? 'Light mode' : 'Dark mode'}</span>
					{/if}
				</button>

				{#if $sidebarCollapsed}
					<button
						type="button"
						onclick={toggleSidebar}
						aria-expanded="false"
						aria-controls="sidebar"
						aria-label="Expand sidebar"
						title="Expand sidebar"
						class="btn btn-ghost group h-8 w-full justify-center px-0 text-xs"
					>
						<PanelLeftOpen
							size={14}
							strokeWidth={2}
							aria-hidden="true"
							class="transition-transform duration-200 group-hover:scale-105"
						/>
					</button>
				{/if}
			</div>
		</div>

		{#if !$sidebarCollapsed}
			<p class="eyebrow pt-2 text-center">v2 · local</p>
		{/if}
	</div>
</aside>
