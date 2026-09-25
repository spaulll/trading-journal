<script lang="ts">
	import { onMount } from 'svelte';
	import { fade } from 'svelte/transition';
	import EquityChart from '$lib/components/charts/EquityChart.svelte';
	import OutcomeDonut from '$lib/components/charts/OutcomeDonut.svelte';
	import TagPerformanceBar from '$lib/components/charts/TagPerformanceBar.svelte';
	import UnderwaterChart from '$lib/components/charts/UnderwaterChart.svelte';
	import KpiStrip from '$lib/components/dashboard/KpiStrip.svelte';
	import LongShortOverview from '$lib/components/dashboard/LongShortOverview.svelte';
	import MonthlyCalendar from '$lib/components/dashboard/MonthlyCalendar.svelte';
	import RadarAnalytics from '$lib/components/dashboard/RadarAnalytics.svelte';
	import SessionGrid from '$lib/components/dashboard/SessionGrid.svelte';
	import StatPanels from '$lib/components/dashboard/StatPanels.svelte';
	import StateBlock from '$lib/components/StateBlock.svelte';
	import {
		api,
		errMsg,
		type ActivityStreaks,
		type CalendarDay,
		type DirectionStats,
		type EquityPoint,
		type KpiDashboard,
		type MonthlyCalendarDto,
		type RadarProfiles,
		type SummaryDto,
		type TagPerf
	} from '$lib/api';

	let loading = $state(true);
	let error = $state<string | null>(null);
	let summary = $state<SummaryDto | null>(null);
	let points = $state<EquityPoint[]>([]);
	let tags = $state<TagPerf[]>([]);
	let days = $state<CalendarDay[]>([]);
	let year = $state(new Date().getFullYear());
	// PLAN-v2 Phase 4 widgets.
	let kpi = $state<KpiDashboard | null>(null);
	let monthData = $state<MonthlyCalendarDto | null>(null);
	let monthCursor = $state({ y: new Date().getFullYear(), m: new Date().getMonth() + 1 });
	let activity = $state<ActivityStreaks | null>(null);
	let longShort = $state<{ buy: DirectionStats; sell: DirectionStats } | null>(null);
	let radarData = $state<RadarProfiles | null>(null);

	async function loadYearDays(y: number): Promise<void> {
		try {
			const c = await api.calendar(y);
			days = c.days;
			year = c.year;
		} catch (e) {
			error = errMsg(e);
		}
	}

	async function load(): Promise<void> {
		loading = true;
		error = null;
		try {
			const [s, e, t, c, k, mc, a, ls, rd] = await Promise.all([
				api.summary(),
				api.equityCurve(),
				api.tagPerformance(),
				api.calendar(year),
				api.kpi(),
				api.monthlyCalendar(monthCursor.y, monthCursor.m),
				api.activity(),
				api.longShort(),
				api.radar()
			]);
			summary = s;
			points = e.points;
			tags = t.tags;
			days = c.days;
			year = c.year;
			kpi = k;
			monthData = mc;
			monthCursor = { y: mc.year, m: mc.month };
			activity = a;
			longShort = ls;
			radarData = rd;
		} catch (e) {
			error = errMsg(e);
		} finally {
			loading = false;
		}
	}

	async function shiftMonth(delta: number): Promise<void> {
		let { y, m } = monthCursor;
		m += delta;
		if (m < 1) {
			m = 12;
			y -= 1;
		}
		if (m > 12) {
			m = 1;
			y += 1;
		}
		try {
			monthData = await api.monthlyCalendar(y, m);
			monthCursor = { y: monthData.year, m: monthData.month };
			if (monthData.year !== year) await loadYearDays(monthData.year);
		} catch (e) {
			error = errMsg(e);
		}
	}

	onMount(() => {
		void load();
	});
</script>

<svelte:head>
	<title>Analytics · Trading Journal</title>
</svelte:head>

{#if loading}
	<div class="flex flex-col gap-4" aria-hidden="true">
		<div class="grid grid-cols-2 gap-4 lg:grid-cols-4">
			{#each Array(4) as _, i}
				<div
					class="h-28 animate-pulse rounded-xl border border-slate-200 bg-gradient-to-r from-slate-100 via-slate-50 to-slate-100 shadow-card dark:border-white/[0.07] dark:from-surface-900 dark:via-white/[0.04] dark:to-surface-900"
					style="animation-delay: {i * 80}ms"
				></div>
			{/each}
		</div>
		<div class="h-72 animate-pulse rounded-xl border border-slate-200 shadow-card dark:border-white/[0.07] dark:bg-surface-900"></div>
		<div class="grid grid-cols-1 gap-4 md:grid-cols-2">
			{#each Array(2) as _}
				<div class="h-72 animate-pulse rounded-xl border border-slate-200 shadow-card dark:border-white/[0.07] dark:bg-surface-900"></div>
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
		body="Log trades with the Telegram bot to unlock performance analytics."
		actionLabel="Back to trades"
		onAction={() => (window.location.href = '/')}
	/>
{:else}
	<div class="flex flex-col gap-4" transition:fade={{ duration: 150 }}>
		{#if kpi}
			<KpiStrip {kpi} />
		{/if}

		<section class="grid grid-cols-1 gap-4 xl:grid-cols-5">
			<div class="rounded-xl border border-slate-200 bg-white p-4 shadow-card xl:col-span-3 dark:border-white/[0.07] dark:bg-surface-900">
				<h2 class="mb-2 text-[13px] font-semibold tracking-tight text-balance">Equity curve</h2>
				{#if points.length > 0}
					<EquityChart {points} />
				{:else}
					<p class="py-10 text-center text-sm text-slate-500">Not enough data.</p>
				{/if}
			</div>
			<div class="rounded-xl border border-slate-200 bg-white p-4 shadow-card xl:col-span-2 dark:border-white/[0.07] dark:bg-surface-900">
				<h2 class="mb-2 text-[13px] font-semibold tracking-tight text-balance">Drawdown</h2>
				{#if points.length > 0}
					<UnderwaterChart {points} />
				{:else}
					<p class="py-10 text-center text-sm text-slate-500">Not enough data.</p>
				{/if}
			</div>
		</section>

		{#if monthData}
			<MonthlyCalendar
				data={monthData}
				yearDays={days}
				onPrev={() => void shiftMonth(-1)}
				onNext={() => void shiftMonth(1)}
			/>
		{/if}

		{#if kpi}
			<SessionGrid {kpi} />
		{/if}

		{#if longShort && activity}
			<LongShortOverview {longShort} {activity} />
		{/if}

		{#if activity}
			<StatPanels {activity} />
		{/if}

		<section class="grid grid-cols-1 gap-4 md:grid-cols-2">
			<div class="rounded-xl border border-slate-200 bg-white p-4 shadow-card dark:border-white/[0.07] dark:bg-surface-900">
				<h2 class="mb-2 text-[13px] font-semibold tracking-tight text-balance">Win / loss / breakeven</h2>
				<OutcomeDonut {summary} />
			</div>
			<div class="rounded-xl border border-slate-200 bg-white p-4 shadow-card dark:border-white/[0.07] dark:bg-surface-900">
				<h2 class="mb-2 text-[13px] font-semibold tracking-tight text-balance">Tag performance</h2>
				<TagPerformanceBar {tags} />
			</div>
		</section>

		{#if radarData}
			<RadarAnalytics radar={radarData} />
		{/if}
	</div>
{/if}
