<script lang="ts">
	import { onMount } from 'svelte';
	import { fade } from 'svelte/transition';
	import EquityChart from '$lib/components/charts/EquityChart.svelte';
	import OutcomeDonut from '$lib/components/charts/OutcomeDonut.svelte';
	import RDistributionChart from '$lib/components/charts/RDistributionChart.svelte';
	import TagPerformanceBar from '$lib/components/charts/TagPerformanceBar.svelte';
	import UnderwaterChart from '$lib/components/charts/UnderwaterChart.svelte';
	import CalendarHeatmap from '$lib/components/dashboard/CalendarHeatmap.svelte';
	import StateBlock from '$lib/components/StateBlock.svelte';
	import { api, errMsg, type CalendarDay, type EquityPoint, type RBucket, type SummaryDto, type TagPerf } from '$lib/api';
	import { fmtMoney, pnlTone, toneText } from '$lib/utils/format';

	let loading = $state(true);
	let error = $state<string | null>(null);
	let summary = $state<SummaryDto | null>(null);
	let points = $state<EquityPoint[]>([]);
	let buckets = $state<RBucket[]>([]);
	let tags = $state<TagPerf[]>([]);
	let days = $state<CalendarDay[]>([]);
	let year = $state(new Date().getFullYear());

	async function load(): Promise<void> {
		loading = true;
		error = null;
		try {
			const [s, e, r, t, c] = await Promise.all([
				api.summary(),
				api.equityCurve(),
				api.rDistribution(),
				api.tagPerformance(),
				api.calendar(year)
			]);
			summary = s;
			points = e.points;
			buckets = r.buckets;
			tags = t.tags;
			days = c.days;
			year = c.year;
		} catch (e) {
			error = errMsg(e);
		} finally {
			loading = false;
		}
	}

	async function shiftYear(delta: number): Promise<void> {
		year += delta;
		try {
			const c = await api.calendar(year);
			days = c.days;
			year = c.year;
		} catch (e) {
			error = errMsg(e);
		}
	}

	onMount(() => {
		void load();
	});

	const stats = $derived(
		summary
			? [
					{ label: 'Net PnL', value: fmtMoney(summary.net_pnl), tone: pnlTone(summary.net_pnl) },
					{ label: 'Win rate', value: `${summary.win_rate.toFixed(1)}%`, tone: summary.win_rate >= 50 ? 'win' as const : 'loss' as const },
					{ label: 'Profit factor', value: summary.profit_factor === null ? '—' : summary.profit_factor.toFixed(2), tone: 'be' as const },
					{ label: 'Expectancy', value: fmtMoney(summary.expectancy), tone: pnlTone(summary.expectancy) },
					{ label: 'Avg win', value: fmtMoney(summary.avg_win), tone: 'win' as const },
					{ label: 'Avg loss', value: fmtMoney(summary.avg_loss), tone: 'loss' as const },
					{ label: 'Max drawdown', value: fmtMoney(summary.max_drawdown), tone: summary.max_drawdown < 0 ? 'loss' as const : 'be' as const },
					{ label: 'Trades', value: `${summary.total_trades}`, tone: 'be' as const }
				]
			: []
	);
</script>

<svelte:head>
	<title>Analytics · Trading Journal</title>
</svelte:head>

{#if loading}
	<div class="flex flex-col gap-4" aria-hidden="true">
		<div class="grid grid-cols-2 gap-4 lg:grid-cols-4">
			{#each Array(8) as _, i}
				<div
					class="h-20 animate-pulse rounded-xl border border-slate-200 bg-gradient-to-r from-slate-100 via-slate-50 to-slate-100 dark:border-slate-800 dark:from-surface-900 dark:via-surface-800 dark:to-surface-900"
					style="animation-delay: {i * 80}ms"
				></div>
			{/each}
		</div>
		<div class="h-72 animate-pulse rounded-xl border border-slate-200 dark:border-slate-800 dark:bg-surface-900"></div>
		<div class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
			{#each Array(3) as _}
				<div class="h-72 animate-pulse rounded-xl border border-slate-200 dark:border-slate-800 dark:bg-surface-900"></div>
			{/each}
		</div>
	</div>
{:else if error || !summary}
	<StateBlock
		kind="error"
		title="Couldn't load analytics"
		body="{error ?? 'Unknown error'} — start the API and retry."
		actionLabel="Retry"
		onAction={() => void load()}
	/>
{:else if summary.total_trades === 0}
	<StateBlock
		title="No closed trades yet"
		body="Sync trades from the Telegram bot to unlock equity, R-distribution and tag analytics."
		actionLabel="Back to trades"
		onAction={() => (window.location.href = '/')}
	/>
{:else}
	<div class="flex flex-col gap-4" transition:fade={{ duration: 150 }}>
		<section class="grid grid-cols-2 gap-4 lg:grid-cols-4" aria-label="Summary stats">
			{#each stats as s}
				<div class="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-surface-900">
					<p class="text-xs text-slate-500 dark:text-slate-400">{s.label}</p>
					<p class="mt-1 font-mono text-xl font-semibold tabular-nums {toneText[s.tone]}">{s.value}</p>
				</div>
			{/each}
		</section>

		<section class="grid grid-cols-1 gap-4 xl:grid-cols-5">
			<div class="rounded-xl border border-slate-200 bg-white p-4 xl:col-span-3 dark:border-slate-800 dark:bg-surface-900">
				<h2 class="mb-2 text-sm font-medium">Equity curve</h2>
				{#if points.length > 0}
					<EquityChart {points} />
				{:else}
					<p class="py-10 text-center text-sm text-slate-500">Not enough data.</p>
				{/if}
			</div>
			<div class="rounded-xl border border-slate-200 bg-white p-4 xl:col-span-2 dark:border-slate-800 dark:bg-surface-900">
				<h2 class="mb-2 text-sm font-medium">Drawdown</h2>
				{#if points.length > 0}
					<UnderwaterChart {points} />
				{:else}
					<p class="py-10 text-center text-sm text-slate-500">Not enough data.</p>
				{/if}
			</div>
		</section>

		<section class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
			<div class="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-surface-900">
				<h2 class="mb-2 text-sm font-medium">R-distribution</h2>
				<RDistributionChart {buckets} />
			</div>
			<div class="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-surface-900">
				<h2 class="mb-2 text-sm font-medium">Win / loss / breakeven</h2>
				<OutcomeDonut {summary} />
			</div>
			<div class="rounded-xl border border-slate-200 bg-white p-4 md:col-span-2 xl:col-span-1 dark:border-slate-800 dark:bg-surface-900">
				<h2 class="mb-2 text-sm font-medium">Tag performance</h2>
				<TagPerformanceBar {tags} />
			</div>
		</section>

		<section class="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-surface-900" aria-label="Calendar heatmap">
			<div class="mb-2 flex items-center justify-between">
				<h2 class="text-sm font-medium">Calendar · {year}</h2>
				<div class="flex items-center gap-1">
					<button
						type="button"
						onclick={() => void shiftYear(-1)}
						aria-label="Previous year"
						class="grid h-7 w-7 place-items-center rounded-md border border-slate-200 text-slate-500 transition-all duration-150 hover:text-slate-900 active:scale-95 dark:border-slate-700 dark:text-slate-400 dark:hover:text-white"
					>‹</button>
					<button
						type="button"
						onclick={() => void shiftYear(1)}
						aria-label="Next year"
						class="grid h-7 w-7 place-items-center rounded-md border border-slate-200 text-slate-500 transition-all duration-150 hover:text-slate-900 active:scale-95 dark:border-slate-700 dark:text-slate-400 dark:hover:text-white"
					>›</button>
				</div>
			</div>
			<CalendarHeatmap {days} {year} />
		</section>
	</div>
{/if}
