<script lang="ts">
	import { WifiOff } from 'lucide-svelte';
	import { connected } from '$lib/stores/connection';
	import { offlineMode, snapshotLabel } from '$lib/stores/offline';
</script>

{#if $connected === false || $offlineMode}
	<div
		role="status"
		class="flex items-center gap-2.5 border-b border-amber-500/30 bg-amber-500/10 px-4 py-2 text-[12.5px] leading-snug text-amber-200 sm:px-6 lg:px-8"
	>
		<WifiOff size={14} strokeWidth={2} aria-hidden="true" class="shrink-0" />
		<p class="min-w-0">
			<span class="font-semibold">Offline — read-only.</span>
			<span class="text-amber-200/80">
				Showing {$snapshotLabel}. Writes are disabled until the server is back.
			</span>
		</p>
	</div>
{/if}
