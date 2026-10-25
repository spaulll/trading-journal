<script lang="ts">
	import { page } from '$app/state';
	import { NAV_LINKS, isActiveLink } from '$lib/nav';
</script>

<!-- Mobile / tablet: floating glass tab bar with a precise active marker. -->
<nav
	aria-label="Primary"
	class="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-base/90 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl lg:hidden"
>
	<div
		class="mx-auto grid max-w-2xl gap-px p-1 sm:gap-1 sm:p-2"
		style="grid-template-columns: repeat({NAV_LINKS.length}, minmax(0, 1fr));"
	>
		{#each NAV_LINKS as link (link.href)}
			{@const Icon = link.icon}
			{@const isActive = isActiveLink(link.href, page.url.pathname)}
			<a
				href={link.href}
				aria-current={isActive ? 'page' : undefined}
				title={link.label}
				class="group relative flex min-w-0 flex-col items-center justify-center gap-0.5 overflow-hidden rounded-control py-1.5 text-xs leading-none transition-[background-color,color,box-shadow,transform] duration-200 ease-spring sm:flex-row sm:gap-1 sm:px-1 sm:py-2.5 sm:text-xs {isActive
					? 'bg-raised text-fg shadow-inset-highlight ring-1 ring-line ring-inset active:bg-raised'
					: 'text-mut hover:bg-raised/40 hover:text-fg active:bg-raised/60'}"
			>
				<span
					class="absolute top-0 left-1/2 h-[2px] w-8 -translate-x-1/2 rounded-full bg-accent transition-opacity duration-200 {isActive
						? 'opacity-100'
						: 'opacity-0'}"
					aria-hidden="true"
				></span>
				<Icon
					size={17}
					strokeWidth={isActive ? 2 : 1.6}
					class="shrink-0 transition-transform duration-200 ease-spring {isActive
						? 'scale-105 text-accent'
						: 'group-hover:-translate-y-0.5'}"
					aria-hidden="true"
				/>
				<span class="whitespace-nowrap font-medium tracking-[-0.01em]">{link.label}</span>
			</a>
		{/each}
	</div>
</nav>
