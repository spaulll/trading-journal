<script lang="ts">
	const { rows = 5 }: { rows?: number } = $props();
</script>

<div class="mt-9" aria-hidden="true">
	<div class="mb-3 flex flex-wrap items-center gap-2">
		<div class="skeleton h-9 w-40 rounded-control"></div>
		<div class="skeleton ml-auto h-9 min-w-40 flex-1 rounded-control sm:max-w-56"></div>
		<div class="skeleton h-9 min-w-28 flex-1 rounded-control sm:max-w-44"></div>
		<div class="skeleton h-9 w-24 rounded-control"></div>
		<div class="skeleton h-9 w-24 rounded-control"></div>
		<div class="skeleton h-9 w-20 rounded-control"></div>
	</div>

	<div class="card hidden overflow-hidden md:block">
		<div class="flex items-center gap-4 border-b border-line px-4 py-3">
			{#each Array(8) as _, i (i)}
				<div class="skeleton h-2.5 flex-1 rounded"></div>
			{/each}
		</div>
		{#each Array(rows) as _, i (i)}
			<div class="flex items-center gap-4 border-b border-line px-4 py-4 last:border-b-0">
				{#each Array(8) as _, c (c)}
					<div class="skeleton h-3 flex-1 rounded"></div>
				{/each}
			</div>
		{/each}
	</div>

	<div class="grid grid-cols-1 gap-2.5 md:hidden">
		{#each Array(rows) as _, i (i)}
			<div class="card min-h-[6.25rem] p-3.5">
				<div class="flex items-center justify-between gap-2">
					<div class="skeleton h-4 w-24 rounded"></div>
					<div class="skeleton h-4 w-16 rounded"></div>
				</div>
				<div class="mt-2 flex items-center justify-between gap-2">
					<div class="skeleton h-3 w-28 rounded"></div>
					<div class="skeleton h-3 w-12 rounded"></div>
				</div>
				<div class="skeleton mt-2 h-4 w-20 rounded"></div>
			</div>
		{/each}
	</div>

	<div class="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-line pt-3">
		<div class="skeleton h-3 w-32 rounded"></div>
		<div class="flex items-center gap-2">
			<div class="skeleton h-8 w-16 rounded-control"></div>
			<div class="skeleton h-8 w-16 rounded-control"></div>
		</div>
	</div>
</div>
