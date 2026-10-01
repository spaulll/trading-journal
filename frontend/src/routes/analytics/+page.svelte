<script lang="ts">
	import { onMount } from 'svelte';
	import { fade } from 'svelte/transition';
	import EquityChart from '$lib/components/charts/EquityChart.svelte';
	import OutcomeDonut from '$lib/components/charts/OutcomeDonut.svelte';
	import RDistributionChart from '$lib/components/charts/RDistributionChart.svelte';
	import TagPerformanceBar from '$lib/components/charts/TagPerformanceBar.svelte';
	import UnderwaterChart from '$lib/components/charts/UnderwaterChart.svelte';
	import KpiStrip from '$lib/components/dashboard/KpiStrip.svelte';
	import LongShortOverview from '$lib/components/dashboard/LongShortOverview.svelte';
	import MonthlyCalendar from '$lib/components/dashboard/MonthlyCalendar.svelte';
	import RadarAnalytics from '$lib/components/dashboard/RadarAnalytics.svelte';
	import SessionGrid from '$lib/components/dashboard/SessionGrid.svelte';
	import StatPanels from '$lib/components/dashboard/StatPanels.svelte';
	import PageHead from '$lib/components/PageHead.svelte';
	import StateBlock from '$lib/components/StateBlock.svelte';
	import DayPanel from '$lib/components/DayPanel.svelte';
	import TradeModal from '$lib/components/TradeModal.svelte';
	import { loadTrades } from '$lib/stores/trades';
	import { markOffline, markOnline, snapshotAt } from '$lib/stores/offline';
	import { SNAPSHOT_KEYS, readSnapshot, saveSnapshot } from '$lib/offline-snapshot';
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
		type RBucket,
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
	let rBuckets = $state<RBucket[]>([]);
	// PLAN-v2 Phase 4 widgets.
	let kpi = $state<KpiDashboard | null>(null);
	let monthData = $state<MonthlyCalendarDto | null>(null);
	let monthCursor = $state({ y: new Date().getFullYear(), m: new Date().getMonth() + 1 });
	let activity = $state<ActivityStreaks | null>(null);
	let longShort = $state<{ buy: DirectionStats; sell: DirectionStats; all?: DirectionStats } | null>(null);
	let radarData = $state<RadarProfiles | null>(null);
	let snapshotRestored = $state(false);

	interface AnalyticsSnapshot {
		summary: SummaryDto;
		points: EquityPoint[];
		tags: TagPerf[];
		days: CalendarDay[];
		year: number;
		kpi: KpiDashboard | null;
		monthData: MonthlyCalendarDto | null;
		monthCursor: { y: number; m: number };
		activity: ActivityStreaks | null;
		longShort: { buy: DirectionStats; sell: DirectionStats; all?: DirectionStats } | null;
		radarData: RadarProfiles | null;
		rBuckets: RBucket[];
	}

	function applySnapshot(snap: AnalyticsSnapshot): void {
		summary = snap.summary;
		points = snap.points;
		tags = snap.tags;
		days = snap.days;
		year = snap.year;
		kpi = snap.kpi;
		monthData = snap.monthData;
		if (snap.monthCursor) monthCursor = snap.monthCursor;
		activity = snap.activity;
		longShort = snap.longShort;
		radarData = snap.radarData;
		rBuckets = snap.rBuckets;
	}

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
			const [s, e, t, c, k, mc, a, ls, rd, rb] = await Promise.all([
				api.summary(),
				api.equityCurve(),
				api.tagPerformance(),
				api.calendar(year),
				api.kpi(),
				api.monthlyCalendar(monthCursor.y, monthCursor.m),
				api.activity(),
				api.longShort(),
				api.radar(),
				api.rDistribution()
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
			rBuckets = rb.buckets;
			snapshotRestored = false;
			markOnline();
			snapshotAt.set(
				saveSnapshot<AnalyticsSnapshot>(SNAPSHOT_KEYS.analytics, {
					summary: s,
					points: e.points,
					tags: t.tags,
					days: c.days,
					year: c.year,
					kpi: k,
					monthData: mc,
					monthCursor: { y: mc.year, m: mc.month },
					activity: a,
					longShort: ls,
					radarData: rd,
					rBuckets: rb.buckets
				}) ?? null
			);
		} catch (e) {
			// Server unreachable: restore the last labelled snapshot (read-only).
			const snap = readSnapshot<AnalyticsSnapshot>(SNAPSHOT_KEYS.analytics);
			if (snap && snap.data.summary) {
				applySnapshot(snap.data);
				snapshotRestored = true;
				markOffline(snap.savedAt);
				error = null;
			} else {
				error = errMsg(e);
			}
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

	async function shiftYear(delta: number): Promise<void> {
		const y = monthCursor.y + delta;
		const m = monthCursor.m;
		try {
			monthData = await api.monthlyCalendar(y, m);
			monthCursor = { y: monthData.year, m: monthData.month };
			await loadYearDays(monthData.year);
		} catch (e) {
			error = errMsg(e);
		}
	}

	onMount(() => {
		void load();
		void loadTrades(true);
	});
</script>

<svelte:head>
	<title>Analytics · Trading Journal</title>
</svelte:head>

{#if loading}
	<div class="flex flex-col gap-4" aria-hidden="true">
		<div class="skeleton h-24 w-full"></div>
		<div class="grid grid-cols-2 gap-4 lg:grid-cols-4">
			{#each Array(4) as _, i}
				<div class="skeleton h-28" style="animation-delay: {i * 80}ms"></div>
			{/each}
		</div>
		<div class="skeleton h-72 w-full"></div>
		<div class="grid grid-cols-1 gap-4 md:grid-cols-2">
			{#each Array(2) as _}
				<div class="skeleton h-72 w-full"></div>
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
		<PageHead
			eyebrow="Performance"
			title="Analytics"
			meta="{summary.total_trades} closed trades · {year} · expectancy, risk &amp; distribution{snapshotRestored
				? ' · offline snapshot'
				: ''}"
		/>

		{#if kpi}
			<KpiStrip {kpi} />
		{/if}

		<section class="rise grid grid-cols-1 gap-4 xl:grid-cols-12" style="animation-delay: 40ms">
			<div class="card p-5 xl:col-span-8">
				<h2 class="eyebrow mb-3">Equity curve</h2>
				{#if points.length > 0}
					<EquityChart {points} />
				{:else}
					<p class="py-10 text-center text-sm text-mut">Not enough data.</p>
				{/if}
			</div>
			<div class="card p-5 xl:col-span-4">
				<h2 class="eyebrow mb-3">Drawdown</h2>
				{#if points.length > 0}
					<UnderwaterChart {points} />
				{:else}
					<p class="py-10 text-center text-sm text-mut">Not enough data.</p>
				{/if}
			</div>
		</section>

		{#if monthData}
			<MonthlyCalendar
				data={monthData}
				yearDays={days}
				onPrev={() => void shiftMonth(-1)}
				onNext={() => void shiftMonth(1)}
				onPrevYear={() => void shiftYear(-1)}
				onNextYear={() => void shiftYear(1)}
			/>
		{/if}

		<!-- Composition plane: outcome donut · tag performance · R distribution -->
		<section class="rise grid grid-cols-1 items-stretch gap-4 lg:grid-cols-3" style="animation-delay: 160ms">
			<div class="card flex flex-col p-5">
				<h2 class="eyebrow mb-3">Win / loss / breakeven</h2>
				<div class="flex-1"><OutcomeDonut {summary} /></div>
			</div>
			<div class="card flex flex-col p-5">
				<h2 class="eyebrow mb-3">Tag performance</h2>
				<div class="flex-1"><TagPerformanceBar {tags} /></div>
			</div>
			<div class="card flex flex-col p-5">
				<h2 class="eyebrow mb-3">R multiple distribution</h2>
				<div class="flex-1">
					{#if rBuckets.length > 0}
						<RDistributionChart buckets={rBuckets} />
					{:else}
						<p class="py-10 text-center text-sm text-mut">Not enough data.</p>
					{/if}
				</div>
			</div>
		</section>

		<!-- Long / short runs alone on its own plane, full bleed. -->
		{#if longShort && activity}
			<LongShortOverview {longShort} {activity} />
		{/if}

		{#if kpi}
			<SessionGrid {kpi} />
		{/if}

		{#if radarData}
			<RadarAnalytics radar={radarData} />
		{/if}

		{#if activity}
			<StatPanels {activity} />
		{/if}
	</div>
{/if}

<DayPanel />
<TradeModal />
