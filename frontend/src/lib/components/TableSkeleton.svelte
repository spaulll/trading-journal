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
		<div class="ledger-scroll overflow-auto">
			<div class="min-w-[960px]">
				<div class="tgrid border-b border-line bg-panel">
					<div class="flex items-center justify-center px-1 py-2.5">
						<div class="skeleton h-4 w-4 rounded"></div>
					</div>
					{#each Array(7) as _, i (i)}
						<div class="px-3 py-2.5">
							<div class="skeleton h-2.5 rounded {i === 6 ? 'ml-auto w-12' : 'w-16'}"></div>
						</div>
					{/each}
				</div>
				{#each Array(rows) as _, i (i)}
					<div class="tgrid row-line min-h-[40px]">
						<div class="flex items-center justify-center px-1 py-[7px]">
							<div class="skeleton h-6 w-6 rounded-md"></div>
						</div>
						<div class="px-3 py-[7px]">
							<div class="skeleton h-3 w-24 rounded"></div>
						</div>
						<div class="px-3 py-[7px]">
							<div class="skeleton h-3 w-20 rounded"></div>
						</div>
						<div class="px-3 py-[7px]">
							<div class="skeleton ml-auto h-3 w-24 rounded"></div>
						</div>
						<div class="px-3 py-[7px]">
							<div class="skeleton ml-auto h-3 w-16 rounded"></div>
						</div>
						<div class="px-3 py-[7px]">
							<div class="skeleton ml-auto h-3 w-10 rounded"></div>
						</div>
						<div class="px-3 py-[7px]">
							<div class="skeleton h-4 w-20 rounded"></div>
						</div>
						<div class="px-3 py-[7px]">
							<div class="skeleton ml-auto h-4 w-12 rounded"></div>
						</div>
					</div>
				{/each}
			</div>
		</div>
	</div>

	<div class="grid grid-cols-1 gap-2.5 md:hidden">
		{#each Array(rows) as _, i (i)}
			<div class="card min-h-[122px] p-3.5">
				<div class="flex items-center justify-between gap-2">
					<div class="skeleton h-4 w-28 rounded"></div>
					<div class="skeleton h-4 w-16 rounded"></div>
				</div>
				<div class="mt-2 flex items-center justify-between gap-2">
					<div class="skeleton h-3 w-32 rounded"></div>
					<div class="skeleton h-3 w-12 rounded"></div>
				</div>
				<div class="mt-1 flex items-center justify-between gap-2">
					<div class="skeleton h-3 w-28 rounded"></div>
					<div class="skeleton h-3 w-10 rounded"></div>
				</div>
				<div class="mt-2 flex gap-1">
					<div class="skeleton h-4 w-20 rounded"></div>
					<div class="skeleton h-4 w-14 rounded"></div>
				</div>
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
