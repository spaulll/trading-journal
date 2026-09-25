<script lang="ts">
	import { page } from '$app/state';
	import { ArrowLeftRight, Activity } from 'lucide-svelte';

	const links = [
		{ href: '/', label: 'Trades', icon: ArrowLeftRight },
		{ href: '/analytics', label: 'Analytics', icon: Activity }
	];

	function active(href: string): boolean {
		return href === '/' ? page.url.pathname === '/' : page.url.pathname.startsWith(href);
	}
</script>

<!-- Desktop sidebar -->
<aside
	class="fixed inset-y-0 left-0 z-40 hidden w-60 flex-col border-r border-slate-200 bg-white shadow-card lg:flex dark:border-white/[0.07] dark:bg-surface-900"
>
	<div class="flex h-16 items-center gap-2.5 border-b border-slate-200 px-5 dark:border-white/[0.07]">
		<span class="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-emerald-500 font-mono text-sm font-bold text-white shadow-lift">J</span>
		<span class="text-sm font-semibold tracking-tight text-balance">Trading Journal</span>
	</div>
	<nav aria-label="Primary" class="flex flex-col gap-1 p-3">
		{#each links as link}
			{@const Icon = link.icon}
			{@const isActive = active(link.href)}
			<a
				href={link.href}
				aria-current={isActive ? 'page' : undefined}
				class="relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-all duration-150 focus-visible:outline-emerald-500 {isActive
					? 'bg-slate-100 font-semibold text-slate-900 dark:bg-white/[0.07] dark:text-white'
					: 'text-slate-500 hover:bg-slate-50 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-white/[0.04] dark:hover:text-white'}"
			>
				<span
					class="absolute top-1/2 left-0 h-5 w-1 -translate-y-1/2 rounded-r-full bg-emerald-500 transition-all duration-200 {isActive
						? 'scale-y-100 opacity-100'
						: 'scale-y-0 opacity-0'}"
					aria-hidden="true"
				></span>
				<Icon size={18} strokeWidth={1.8} aria-hidden="true" />
				{link.label}
			</a>
		{/each}
	</nav>
	<div class="mt-auto border-t border-slate-200 p-4 dark:border-white/[0.07]">
		<p class="font-mono text-[11px] tracking-wide text-slate-400 tabular-nums dark:text-slate-500">self-hosted · sqlite</p>
	</div>
</aside>

<!-- Mobile bottom glass bar -->
<nav
	aria-label="Primary"
	class="fixed inset-x-0 bottom-0 z-40 border-t border-slate-200 bg-white/85 pb-[env(safe-area-inset-bottom)] backdrop-blur-md lg:hidden dark:border-white/[0.07] dark:bg-surface-950/85"
>
	<div class="grid grid-cols-2">
		{#each links as link}
			{@const Icon = link.icon}
			{@const isActive = active(link.href)}
			<a
				href={link.href}
				aria-current={isActive ? 'page' : undefined}
				class="relative flex flex-col items-center gap-1 py-2.5 text-[11px] transition-colors duration-150 focus-visible:outline-emerald-500 {isActive
					? 'font-semibold text-slate-900 dark:text-white'
					: 'text-slate-400 dark:text-slate-500'}"
			>
				<span
					class="absolute top-0 h-0.5 w-10 rounded-full bg-emerald-500 transition-all duration-200 {isActive
						? 'scale-x-100 opacity-100'
						: 'scale-x-0 opacity-0'}"
					aria-hidden="true"
				></span>
				<Icon size={20} strokeWidth={isActive ? 2 : 1.8} aria-hidden="true" />
				{link.label}
			</a>
		{/each}
	</div>
</nav>
