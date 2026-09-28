<script lang="ts">
	import { page } from '$app/state';
	import { NAV_LINKS, isActiveLink } from '$lib/nav';
</script>

<!-- Mobile / tablet: floating glass tab bar with a sliding active plate. -->
<nav
	aria-label="Primary"
	class="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-base/85 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl lg:hidden"
>
	<div
		class="mx-auto grid max-w-md gap-1 p-2"
		style="grid-template-columns: repeat({NAV_LINKS.length}, minmax(0, 1fr));"
	>
		{#each NAV_LINKS as link (link.href)}
			{@const Icon = link.icon}
			{@const isActive = isActiveLink(link.href, page.url.pathname)}
			<a
				href={link.href}
				aria-current={isActive ? 'page' : undefined}
				class="relative flex items-center justify-center gap-2 overflow-hidden rounded-xl py-2.5 text-[13px] transition-all duration-300 ease-spring {isActive
					? 'bg-raised text-fg shadow-[inset_0_1px_0_rgb(255_255_255/0.06)]'
					: 'text-mut hover:text-fg'}"
			>
				<span
					class="absolute inset-x-6 -bottom-px h-px bg-accent transition-opacity duration-300 {isActive
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
				<span class="font-medium">{link.label}</span>
			</a>
		{/each}
	</div>
</nav>
