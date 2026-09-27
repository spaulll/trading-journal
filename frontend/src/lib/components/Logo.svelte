<script lang="ts">
	let {
		size = 32,
		class: className = ''
	}: { size?: number; class?: string } = $props();
</script>

<!--
	Brand mark: app logo (gold journal glyph). Reads down to 16px,
	served from /logo.png with PNG favicon siblings.
-->
<img
	src="/logo.png"
	alt=""
	aria-hidden="true"
	width={size}
	height={size}
	draggable="false"
	fetchpriority="high"
	decoding="async"
	class="shrink-0 rounded-[11px] object-cover shadow-[inset_0_1px_0_rgb(255_255_255/0.07)] ring-1 ring-black/10 dark:ring-white/10 {className}"
	style="width: {size}px; height: {size}px;"
/>
