<script lang="ts">
	let {
		size = 32,
		class: className = ''
	}: { size?: number; class?: string } = $props();
</script>

<!--
	Brand mark: brass glyph — an ascending equity line that resolves in a
	live-price dot. Theme-aware (accent on panel), reads down to 16px.
-->
<span
	class="group/logo relative grid shrink-0 place-items-center rounded-[11px] border border-accent/35 bg-accent/10 text-accent shadow-[inset_0_1px_0_rgb(255_255_255/0.07)] transition-transform duration-300 ease-spring {className}"
	style="width: {size}px; height: {size}px;"
	aria-hidden="true"
>
	<svg
		width={Math.round(size * 0.58)}
		height={Math.round(size * 0.58)}
		viewBox="0 0 24 24"
		fill="none"
		xmlns="http://www.w3.org/2000/svg"
	>
		<path
			d="M3.4 16.2 9.2 10.4l3.4 3.4L20.6 5.8"
			stroke="currentColor"
			stroke-width="2.4"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
		<circle cx="20.6" cy="5.8" r="2.6" fill="currentColor" />
	</svg>
	<span
		class="absolute right-0.5 bottom-0.5 h-1.5 w-1.5 rounded-full bg-accent dot-live"
	></span>
</span>
