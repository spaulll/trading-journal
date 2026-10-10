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
	import { accounts, loadAccounts, selectedAccountId } from '$lib/stores/accounts';
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
		type PropStatusDto,
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
	let prop = $state<PropStatusDto | null>(null);
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
			const c = await api.calendar(y, $selectedAccountId);
			days = c.days;
			year = c.year;
		} catch (e) {
			error = errMsg(e);
		}
	}

	async function load(): Promise<void> {
		loading = true;
		error = null;
		const acct = $selectedAccountId;
		try {
			const [s, e, t, c, k, mc, a, ls, rd, rb] = await Promise.all([
				api.summary(acct),
				api.equityCurve(acct),
				api.tagPerformance(acct),
				api.calendar(year, acct),
				api.kpi(acct),
				api.monthlyCalendar(monthCursor.y, monthCursor.m, acct),
				api.activity(acct),
				api.longShort(acct),
				api.radar(acct),
				api.rDistribution(acct)
			]);
			try {
				prop = acct ? await api.propStatus(acct) : null;
			} catch {
				prop = null;
			}
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
			if (!acct) {
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
			}
		} catch (e) {
			// Server unreachable: restore the last labelled snapshot (overall only).
			if (!acct) {
				const snap = readSnapshot<AnalyticsSnapshot>(SNAPSHOT_KEYS.analytics);
				if (snap && snap.data.summary) {
					applySnapshot(snap.data);
					snapshotRestored = true;
					markOffline(snap.savedAt);
					error = null;
					return;
				}
			}
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
			monthData = await api.monthlyCalendar(y, m, $selectedAccountId);
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
			monthData = await api.monthlyCalendar(y, m, $selectedAccountId);
			monthCursor = { y: monthData.year, m: monthData.month };
			await loadYearDays(monthData.year);
		} catch (e) {
			error = errMsg(e);
		}
	}

	onMount(() => {
		void loadAccounts();
		void load();
		void loadTrades(true);
	});

	function onAccountChange(e: Event): void {
		const v = (e.currentTarget as HTMLSelectElement).value;
		selectedAccountId.set(v ? Number(v) : null);
		void load();
	}
</script>

<svelte:head>
	<title>Analytics · Trading Journal</title>
</svelte:head>

{#snippet accountSwitcher()}
	<label class="flex h-10 items-center gap-2 rounded-xl border border-line bg-raised/70 px-3 text-sm text-dim">
		<span class="font-mono text-[10px] tracking-[0.16em] uppercase">Account</span>
		<select
			value={$selectedAccountId === null ? '' : String($selectedAccountId)}
			onchange={onAccountChange}
			class="h-full max-w-44 appearance-none border-0 bg-transparent text-[13px] text-fg outline-none [color-scheme:inherit] [&>option]:bg-panel [&>option]:text-fg"
			aria-label="Analytics account"
		>
			<option value="">All accounts</option>
			{#each $accounts as a (a.id)}
				<option value={String(a.id)}>@{a.alias}</option>
			{/each}
		</select>
	</label>
{/snippet}

{#snippet propStrip()}
	{#if prop}
		<section class="card rise px-5 py-4" style="animation-delay: 10ms" aria-label="Prop status for @{prop.alias}">
			<div class="grid grid-cols-2 gap-px sm:grid-cols-5">
				<div><p class="eyebrow">Balance</p><p class="num mt-1 text-lg font-semibold text-fg tabular-nums">{prop.balance.toLocaleString()}</p><p class="num mt-0.5 text-[11px] text-dim">{prop.total_net >= 0 ? '+' : ''}{prop.total_net.toLocaleString()} total</p></div>
				<div><p class="eyebrow">Daily left</p><p class="num mt-1 text-lg font-semibold tabular-nums {(prop.daily_left ?? 0) < 0 ? 'text-loss' : 'text-fg'}">{prop.daily_left?.toLocaleString() ?? '—'}</p><p class="num mt-0.5 text-[11px] text-dim">{prop.daily_pnl >= 0 ? '+' : ''}{prop.daily_pnl.toLocaleString()} today · {prop.daily_loss_pct}% ({prop.daily_basis})</p></div>
				<div><p class="eyebrow">Max left</p><p class="num mt-1 text-lg font-semibold tabular-nums {(prop.max_left ?? 1) <= 0 ? 'text-loss' : 'text-fg'}">{prop.max_left?.toLocaleString() ?? '—'}</p><p class="num mt-0.5 text-[11px] text-dim">{prop.max_mode} {prop.max_loss_pct}% · floor {prop.max_floor?.toLocaleString() ?? '—'}</p></div>
				<div><p class="eyebrow">Target</p><p class="num mt-1 text-lg font-semibold text-fg tabular-nums">{prop.target_pct === null ? '—' : `${prop.target_pct.toFixed(1)}%`}</p><p class="num mt-0.5 text-[11px] text-dim">goal {prop.profit_target?.toLocaleString() ?? '—'}{prop.profit_target_pct !== null ? ` (${prop.profit_target_pct}%)` : ''}</p></div>
				<div><p class="eyebrow">Status</p><p class="mt-1 font-mono text-[12px] font-bold tracking-[0.14em] uppercase {prop.breached ? 'text-loss' : 'text-win'}">{prop.breached ? 'breach' : prop.status}</p><p class="num mt-0.5 text-[11px] text-dim">@{prop.alias}</p></div>
			</div>
		</section>
	{/if}
{/snippet}

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
	<div class="flex flex-col gap-4" transition:fade={{ duration: 150 }}>
		<PageHead
			eyebrow="Performance"
			title="Analytics"
			meta={$selectedAccountId === null ? 'overall · all accounts' : 'filtered · one account'}
		>
			{@render accountSwitcher()}
		</PageHead>

		{@render propStrip()}

		<StateBlock
			title="No closed trades yet"
			body={$selectedAccountId === null
				? 'Log trades with the Telegram bot to unlock performance analytics.'
				: 'No closed trades on this account yet — move some over from the Trades page or log with @alias.'}
			actionLabel="Back to trades"
			onAction={() => (window.location.href = '/')}
		/>
	</div>
{:else}
	<div class="flex flex-col gap-4" transition:fade={{ duration: 150 }}>
		<PageHead
			eyebrow="Performance"
			title="Analytics"
			meta="{summary.total_trades} closed trades · {year} · expectancy, risk &amp; distribution{snapshotRestored
				? ' · offline snapshot'
				: ''}"
		>
			{@render accountSwitcher()}
		</PageHead>

		{@render propStrip()}

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
