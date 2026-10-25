<script lang="ts">
	import AnalyticsSection from './AnalyticsSection.svelte';
</script>

{#snippet tableBlock(rows: number, cols: number)}
	<div class="overflow-hidden rounded-control border border-line">
		<div class="flex items-center gap-4 border-b border-line px-3 py-2.5">
			{#each Array(cols) as _, i (i)}
				<div class="skeleton h-2.5 flex-1 rounded"></div>
			{/each}
		</div>
		{#each Array(rows) as _, r (r)}
			<div class="flex items-center gap-4 border-b border-line px-3 py-2.5 last:border-b-0">
				{#each Array(cols) as _, c (c)}
					<div class="skeleton h-3 flex-1 rounded"></div>
				{/each}
			</div>
		{/each}
	</div>
{/snippet}

{#snippet statList(rows: number)}
	<div>
		<div class="skeleton h-3 w-36 rounded"></div>
		<div class="mt-3">
			{#each Array(rows) as _, i (i)}
				<div class="flex items-center justify-between gap-3 border-b border-line py-2 last:border-0">
					<div class="skeleton h-3 w-24 rounded"></div>
					<div class="skeleton h-3 w-16 rounded"></div>
				</div>
			{/each}
		</div>
	</div>
{/snippet}

<div class="flex flex-col gap-6">
	<section
		class="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5"
		aria-label="Key performance indicators"
	>
		<div class="card min-h-[12.75rem] p-5 sm:col-span-2 xl:col-span-2">
			<div class="skeleton h-3 w-24 rounded"></div>
			<div class="skeleton mt-3 h-10 w-44 rounded"></div>
			<div class="skeleton mt-3 h-3 w-32 rounded"></div>
			<div class="skeleton mt-6 h-10 w-full rounded-control"></div>
		</div>
		{#each Array(3) as _, i (i)}
			<div
				class="card min-h-[10rem] p-5 sm:min-h-[10rem] xl:min-h-[12.75rem] {i === 2
					? 'sm:col-span-2 xl:col-span-1'
					: ''}"
			>
				<div class="skeleton h-3 w-20 rounded"></div>
				<div class="skeleton mt-3 h-8 w-24 rounded"></div>
				<div class="skeleton mt-4 h-1.5 w-full rounded-full"></div>
				<div class="skeleton mt-3 h-2.5 w-24 rounded"></div>
			</div>
		{/each}
	</section>

	<AnalyticsSection title="Edge" meta="by symbol · by setup · confidence" delay={40}>
		<div class="flex min-h-[41rem] flex-col gap-5 md:min-h-[35rem]">
			<div>
				<div class="flex items-center justify-between gap-4">
					<div class="skeleton h-3 w-40 rounded"></div>
					<div class="skeleton h-3 w-20 rounded"></div>
				</div>
				<div class="mt-3">{@render tableBlock(3, 6)}</div>
				<div class="skeleton mt-2 h-2.5 w-3/4 rounded"></div>
			</div>
			<div class="border-t border-line pt-5">
				<div class="skeleton h-3 w-44 rounded"></div>
				<div class="mt-3 grid grid-cols-4 gap-2">
					{#each Array(16) as _, i (i)}
						<div class="skeleton h-9 rounded"></div>
					{/each}
				</div>
			</div>
			<div class="border-t border-line pt-5">
				<div class="skeleton h-3 w-48 rounded"></div>
				<div class="skeleton mt-3 h-24 rounded-control"></div>
			</div>
		</div>
	</AnalyticsSection>

	<AnalyticsSection title="Risk" meta="drawdown · ruin" delay={80}>
		<div class="min-h-[34rem] md:min-h-[27.5rem] xl:min-h-0">
			<div class="grid grid-cols-1 gap-5 lg:grid-cols-2">
				{#each Array(2) as _, i (i)}
					<div
						class="min-w-0 {i === 1
							? 'border-t border-line pt-5 lg:border-t-0 lg:border-l lg:pl-5 lg:pt-0'
							: ''}"
					>
						<div class="flex items-center justify-between gap-3">
							<div class="skeleton h-3 w-40 rounded"></div>
							<div class="skeleton h-2.5 w-12 rounded"></div>
						</div>
						<div class="mt-3">{@render tableBlock(1, 4)}</div>
						<div class="skeleton mt-2 h-2.5 w-2/3 rounded"></div>
					</div>
				{/each}
			</div>
			<div class="mt-5 border-t border-line pt-5">
				<div class="flex items-center justify-between gap-3">
					<div class="skeleton h-3 w-36 rounded"></div>
					<div class="skeleton h-2.5 w-20 rounded"></div>
				</div>
				<div class="skeleton mt-3 h-28 rounded-control"></div>
			</div>
		</div>
	</AnalyticsSection>

	<AnalyticsSection title="Curve" meta="equity · underwater" delay={120}>
		<div class="grid grid-cols-1 gap-5 xl:grid-cols-12 xl:gap-0">
			<div class="min-w-0 xl:col-span-8 xl:pr-5">
				<div class="skeleton h-3 w-32 rounded"></div>
				<div class="skeleton mt-3 h-[260px] rounded-control"></div>
			</div>
			<div
				class="min-w-0 border-t border-line pt-5 xl:col-span-4 xl:border-t-0 xl:border-l xl:pl-5 xl:pt-0"
			>
				<div class="skeleton h-3 w-32 rounded"></div>
				<div class="skeleton mt-3 h-[260px] rounded-control"></div>
			</div>
		</div>
	</AnalyticsSection>

	<section class="card p-5" aria-label="Monthly trading calendar">
		<div class="flex flex-wrap items-center justify-between gap-3">
			<div class="skeleton h-6 w-40 rounded"></div>
			<div class="flex flex-wrap items-center gap-2">
				<div class="skeleton h-8 w-16 rounded-control"></div>
				<div class="skeleton h-8 w-16 rounded-control"></div>
			</div>
		</div>
		<div class="mt-5 grid grid-cols-1 gap-5 xl:grid-cols-4">
			<div class="xl:col-span-3">
				<div class="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-5">
					{#each Array(5) as _, i (i)}
						<div class="skeleton h-20 rounded-control"></div>
					{/each}
				</div>
				<div class="grid grid-cols-7 gap-1.5 sm:gap-2">
					{#each Array(35) as _, i (i)}
						<div class="skeleton min-h-16 rounded-xl sm:min-h-20"></div>
					{/each}
				</div>
			</div>
			<div>
				<div class="skeleton h-44 rounded-control"></div>
				<div class="mt-4 grid grid-cols-2 gap-2">
					{#each Array(4) as _, i (i)}
						<div class="skeleton h-16 rounded-control"></div>
					{/each}
				</div>
			</div>
		</div>
	</section>

	<AnalyticsSection title="Composition" meta="outcome · tags · R" delay={200}>
		<div class="grid grid-cols-1 gap-5 lg:grid-cols-3 lg:gap-0">
			<div class="min-w-0 lg:pr-5">
				<div class="skeleton h-3 w-36 rounded"></div>
				<div class="skeleton mt-3 h-64 rounded-control"></div>
			</div>
			<div
				class="min-w-0 border-t border-line pt-5 lg:border-t-0 lg:border-l lg:px-5 lg:pt-0"
			>
				<div class="skeleton h-3 w-32 rounded"></div>
				<div class="skeleton mt-3 h-64 rounded-control"></div>
				<div class="skeleton mt-2 h-2.5 w-40 rounded"></div>
			</div>
			<div
				class="min-w-0 border-t border-line pt-5 lg:border-t-0 lg:border-l lg:pl-5 lg:pt-0"
			>
				<div class="skeleton h-3 w-40 rounded"></div>
				<div class="skeleton mt-3 h-64 rounded-control"></div>
			</div>
		</div>
	</AnalyticsSection>

	<AnalyticsSection title="Direction &amp; sessions" meta="long/short · killzones" delay={240}>
		<div class="min-h-[106.75rem] md:min-h-[78rem] xl:min-h-[41.5rem]">
			<div>
				<div class="mb-5 flex flex-wrap items-center gap-3">
				<div class="skeleton h-3 w-36 rounded"></div>
				<div class="skeleton h-3 w-28 rounded"></div>
				<div class="skeleton ml-auto h-8 w-32 rounded-control"></div>
			</div>
			<div class="grid grid-cols-1 gap-5 lg:grid-cols-12">
				<div class="lg:col-span-4 xl:col-span-3">
					<div class="skeleton h-60 rounded-control"></div>
				</div>
				<div class="min-w-0 lg:col-span-4 xl:col-span-4">
					<div class="skeleton h-3 w-24 rounded"></div>
					<div class="mt-2">
						{#each Array(4) as _, i (i)}
							<div
								class="flex items-center justify-between gap-3 border-b border-line py-2 last:border-0"
							>
								<div class="skeleton h-3 w-16 rounded"></div>
								<div class="skeleton h-3 w-24 rounded"></div>
							</div>
						{/each}
					</div>
				</div>
				<div
					class="min-w-0 border-t border-line pt-5 lg:col-span-4 lg:border-t-0 lg:border-l lg:pl-5 lg:pt-0 xl:col-span-5"
				>
					<div class="skeleton h-3 w-24 rounded"></div>
					<div class="mt-2">
						{#each Array(4) as _, i (i)}
							<div
								class="flex items-center justify-between gap-3 border-b border-line py-2 last:border-0"
							>
								<div class="skeleton h-3 w-16 rounded"></div>
								<div class="skeleton h-3 w-24 rounded"></div>
							</div>
						{/each}
					</div>
				</div>
			</div>
			<div class="mt-6">
				<div class="skeleton h-3 w-40 rounded"></div>
				<div
					class="mt-2 grid grid-cols-2 gap-px overflow-hidden rounded-control border border-line bg-line sm:grid-cols-3 xl:grid-cols-6"
				>
					{#each Array(6) as _, i (i)}
						<div class="min-w-0 bg-panel px-3 py-2.5">
							<div class="skeleton h-2.5 w-14 rounded"></div>
							<div class="skeleton mt-2 h-4 w-20 rounded"></div>
						</div>
					{/each}
				</div>
			</div>
		</div>
		<div class="mt-5 border-t border-line pt-5">
			<div class="flex flex-wrap items-baseline justify-between gap-2">
				<div class="skeleton h-3 w-24 rounded"></div>
				<div class="skeleton h-2.5 w-28 rounded"></div>
			</div>
			<div
				class="mt-3 grid grid-cols-1 gap-px overflow-hidden rounded-control border border-line bg-line sm:grid-cols-2 xl:grid-cols-4"
			>
				{#each Array(4) as _, i (i)}
					<div class="min-w-0 bg-panel p-4">
						<div class="flex items-baseline justify-between gap-2">
							<div class="skeleton h-2.5 w-16 rounded"></div>
							<div class="skeleton h-2.5 w-10 rounded"></div>
						</div>
						<div class="skeleton mt-3 h-6 w-24 rounded"></div>
						<div class="skeleton mt-3 h-2.5 w-20 rounded"></div>
					</div>
				{/each}
			</div>
		</div>
		</div>
	</AnalyticsSection>

	<AnalyticsSection title="Behavior" meta="weekday · session · streaks" delay={280}>
		<div
			class="grid min-h-[81.6rem] grid-cols-1 gap-5 md:min-h-[42.5rem] xl:min-h-[22.3rem] xl:grid-cols-2 xl:gap-0"
		>
			<div class="min-w-0 xl:pr-5">
				<div class="grid grid-cols-1 gap-5 md:grid-cols-2 md:gap-0">
					<div class="min-w-0 md:pr-5">
						<div class="flex items-center justify-between gap-3">
							<div class="skeleton h-3 w-20 rounded"></div>
							<div class="skeleton h-3 w-16 rounded"></div>
						</div>
						<div class="skeleton mt-3 h-64 rounded-control"></div>
						<div class="skeleton mt-2 h-2.5 w-3/4 rounded"></div>
					</div>
					<div
						class="min-w-0 border-t border-line pt-5 md:border-t-0 md:border-l md:pl-5 md:pt-0"
					>
						<div class="flex items-center justify-between gap-3">
							<div class="skeleton h-3 w-24 rounded"></div>
							<div class="skeleton h-3 w-16 rounded"></div>
						</div>
						<div class="skeleton mt-3 h-64 rounded-control"></div>
						<div class="skeleton mt-2 h-2.5 w-3/4 rounded"></div>
					</div>
				</div>
			</div>
			<div
				class="min-w-0 border-t border-line pt-5 xl:border-t-0 xl:border-l xl:pl-5 xl:pt-0"
			>
				<div class="grid grid-cols-1 gap-5 md:grid-cols-2 md:gap-0">
					<div class="min-w-0 md:pr-5">{@render statList(8)}</div>
					<div
						class="min-w-0 border-t border-line pt-5 md:border-t-0 md:border-l md:pl-5 md:pt-0"
					>
						{@render statList(8)}
					</div>
				</div>
			</div>
		</div>
	</AnalyticsSection>
</div>
