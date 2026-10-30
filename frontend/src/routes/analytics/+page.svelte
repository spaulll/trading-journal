<script lang="ts">
	import { onMount } from 'svelte';
	import { fade } from 'svelte/transition';
	import EquityChart from '$lib/components/charts/EquityChart.svelte';
	import OutcomeDonut from '$lib/components/charts/OutcomeDonut.svelte';
	import RDistributionChart from '$lib/components/charts/RDistributionChart.svelte';
	import TagPerformanceBar from '$lib/components/charts/TagPerformanceBar.svelte';
	import UnderwaterChart from '$lib/components/charts/UnderwaterChart.svelte';
	import AnalyticsSection from '$lib/components/dashboard/AnalyticsSection.svelte';
	import AnalyticsSkeleton from '$lib/components/dashboard/AnalyticsSkeleton.svelte';
	import DrawdownBreakdown from '$lib/components/dashboard/DrawdownBreakdown.svelte';
	import KpiStrip from '$lib/components/dashboard/KpiStrip.svelte';
	import LongShortOverview from '$lib/components/dashboard/LongShortOverview.svelte';
	import MonthlyCalendar from '$lib/components/dashboard/MonthlyCalendar.svelte';
	import RadarAnalytics from '$lib/components/dashboard/RadarAnalytics.svelte';
	import RiskOfRuinPanel from '$lib/components/dashboard/RiskOfRuinPanel.svelte';
	import SessionGrid from '$lib/components/dashboard/SessionGrid.svelte';
	import SetupConfidencePanel from '$lib/components/dashboard/SetupConfidencePanel.svelte';
	import SetupMatrix from '$lib/components/dashboard/SetupMatrix.svelte';
	import StatPanels from '$lib/components/dashboard/StatPanels.svelte';
	import SymbolPerformanceTable from '$lib/components/dashboard/SymbolPerformanceTable.svelte';
	import PageHead from '$lib/components/PageHead.svelte';
	import StateBlock from '$lib/components/StateBlock.svelte';
	import DayPanel from '$lib/components/DayPanel.svelte';
	import TradeModal from '$lib/components/TradeModal.svelte';
	import { loadOpenPositions } from '$lib/stores/trades';
	import { accounts, loadAccounts, selectedAccountId } from '$lib/stores/accounts';
	import { markOffline, markOnline, snapshotAt } from '$lib/stores/offline';
	import { SNAPSHOT_KEYS, readSnapshot, saveSnapshot } from '$lib/offline-snapshot';
	import { readOverview, writeOverview } from '$lib/analytics-overview-cache';
	import { fmtMoney } from '$lib/utils/format';
	import {
		api,
		errMsg,
		type ActivityStreaks,
		type AnalyticsOverview,
		type CalendarDay,
		type DirectionStats,
		type DrawdownBreakdown as DrawdownBreakdownDto,
		type EquityPoint,
		type KpiDashboard,
		type MonthlyCalendarDto,
		type PropStatusDto,
		type RadarProfiles,
		type RBucket,
		type RiskOfRuin,
		type SetupConfidence,
		type SetupMatrix as SetupMatrixDto,
		type SummaryDto,
		type SymbolPerformance,
		type TagPerf
	} from '$lib/api';

	let loading = $state(true);
	let error = $state<string | null>(null);
	let summary = $state<SummaryDto | null>(null);
	let points = $state<EquityPoint[]>([]);
	let tags = $state<TagPerf[]>([]);
	let symbolPerf = $state<SymbolPerformance | null>(null);
	let matrix = $state<SetupMatrixDto | null>(null);
	let confidence = $state<SetupConfidence | null>(null);
	let drawdownAccount = $state<DrawdownBreakdownDto | null>(null);
	let drawdownSetup = $state<DrawdownBreakdownDto | null>(null);
	let ruin = $state<RiskOfRuin | null>(null);
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
	/** The server's trading day, not the browser's calendar date. */
	let tradingToday = $state('');

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
		symbolPerf?: SymbolPerformance;
		matrix?: SetupMatrixDto;
		confidence?: SetupConfidence;
		drawdownAccount?: DrawdownBreakdownDto;
		drawdownSetup?: DrawdownBreakdownDto;
		ruin?: RiskOfRuin;
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
		if (snap.symbolPerf) symbolPerf = snap.symbolPerf;
		if (snap.matrix) matrix = snap.matrix;
		if (snap.confidence) confidence = snap.confidence;
		if (snap.drawdownAccount) drawdownAccount = snap.drawdownAccount;
		if (snap.drawdownSetup) drawdownSetup = snap.drawdownSetup;
		if (snap.ruin) ruin = snap.ruin;
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

	/** Flatten the one aggregate payload into the snapshot shape the page already renders. */
	function overviewToSnapshot(o: AnalyticsOverview): AnalyticsSnapshot {
		return {
			summary: o.summary,
			points: o.equity_curve.points,
			tags: o.tag_performance.tags,
			symbolPerf: o.symbol_performance,
			matrix: o.setup_matrix,
			confidence: o.setup_confidence,
			drawdownAccount: o.drawdown_account,
			drawdownSetup: o.drawdown_setup,
			ruin: o.risk_of_ruin,
			days: o.calendar.days,
			year: o.calendar.year,
			kpi: o.kpi_dashboard,
			monthData: o.monthly_calendar,
			monthCursor: { y: o.monthly_calendar.year, m: o.monthly_calendar.month },
			activity: o.activity_and_streaks,
			longShort: o.long_short_stats,
			radarData: o.radar_profiles,
			rBuckets: o.r_distribution.buckets
		};
	}

	/** Account + period → the key the module-scope overview cache is stored under. */
	const overviewKey = (acct: number | null, y: number, m: number): string =>
		`${acct ?? 'all'}|${y}|${m}`;

	async function load(): Promise<void> {
		const acct = $selectedAccountId;
		const key = overviewKey(acct, year, monthCursor.m);
		const cached = readOverview(key);
		if (cached) {
			// Stale-while-revalidate: show the last result now, confirm it below.
			applySnapshot(overviewToSnapshot(cached.data));
			loading = false;
		} else {
			loading = true;
		}
		error = null;
		try {
			const overview = await api.analyticsOverview(acct, year, monthCursor.m);
			writeOverview(key, overview);
			const snap = overviewToSnapshot(overview);
			applySnapshot(snap);
			snapshotRestored = false;
			markOnline();
			if (!acct) {
				snapshotAt.set(saveSnapshot<AnalyticsSnapshot>(SNAPSHOT_KEYS.analytics, snap) ?? null);
			}
			try {
				prop = acct ? await api.propStatus(acct) : null;
			} catch {
				prop = null;
			}
		} catch (e) {
			// We already have fresh-enough data on screen — keep it, don't flash an error.
			if (cached) {
				snapshotRestored = true;
				markOffline(new Date(cached.at).toISOString());
				return;
			}
			// Server unreachable: restore the last labelled snapshot (overall only).
			if (!acct) {
				const snapshot = readSnapshot<AnalyticsSnapshot>(SNAPSHOT_KEYS.analytics);
				if (snapshot && snapshot.data.summary) {
					applySnapshot(snapshot.data);
					snapshotRestored = true;
					markOffline(snapshot.savedAt);
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
		void loadOpenPositions();
		void api
			.getTradingDay()
			.then((d) => (tradingToday = d.today))
			.catch(() => {
				// The calendar falls back to the browser's date.
			});
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
	<label
		class="flex h-10 items-center gap-2 rounded-control border border-line bg-raised/70 px-3 text-sm text-dim transition-[border-color,box-shadow,background-color] duration-200 focus-within:border-accent/60 focus-within:bg-raised focus-within:ring-2 focus-within:ring-accent/20"
	>
		<span class="font-mono text-xs tracking-[0.16em] uppercase">Account</span>
		<select
			value={$selectedAccountId === null ? '' : String($selectedAccountId)}
			onchange={onAccountChange}
			class="h-full max-w-44 appearance-none border-0 bg-transparent text-sm text-fg outline-none focus:ring-0 [color-scheme:inherit] [&>option]:bg-panel [&>option]:text-fg"
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
				<div><p class="eyebrow">Balance · {prop.base_currency}</p><p class="num mt-1 text-lg font-semibold text-fg tabular-nums">{prop.balance.toLocaleString()}</p><p class="num mt-0.5 text-[11px] text-dim">{prop.total_net >= 0 ? '+' : ''}{prop.total_net.toLocaleString()} total{#if prop.base_currency !== 'USD'}{' '}<span class="text-dim">· ≈ {fmtMoney(prop.total_net_usd)}</span>{/if}</p></div>
				<div><p class="eyebrow">Daily left · {prop.base_currency}</p><p class="num mt-1 text-lg font-semibold tabular-nums {(prop.daily_left ?? 0) < 0 ? 'text-loss' : 'text-fg'}">{prop.daily_left?.toLocaleString() ?? '—'}</p><p class="num mt-0.5 text-[11px] text-dim">{prop.daily_pnl >= 0 ? '+' : ''}{prop.daily_pnl.toLocaleString()} today · {prop.daily_loss_pct}% ({prop.daily_basis})</p></div>
				<div><p class="eyebrow">Max left · {prop.base_currency}</p><p class="num mt-1 text-lg font-semibold tabular-nums {(prop.max_left ?? 1) <= 0 ? 'text-loss' : 'text-fg'}">{prop.max_left?.toLocaleString() ?? '—'}</p><p class="num mt-0.5 text-[11px] text-dim">{prop.max_mode} {prop.max_loss_pct}% · floor {prop.max_floor?.toLocaleString() ?? '—'}</p></div>
				<div><p class="eyebrow">Target · {prop.base_currency}</p><p class="num mt-1 text-lg font-semibold text-fg tabular-nums">{prop.target_pct === null ? '—' : `${prop.target_pct.toFixed(1)}%`}</p><p class="num mt-0.5 text-[11px] text-dim">goal {prop.profit_target?.toLocaleString() ?? '—'}{prop.profit_target_pct !== null ? ` (${prop.profit_target_pct}%)` : ''}</p></div>
				<div><p class="eyebrow">Status</p><p class="mt-1 font-mono text-[12px] font-bold tracking-[0.14em] uppercase {prop.breached ? 'text-loss' : 'text-win'}">{prop.breached ? 'breach' : prop.status}</p><p class="num mt-0.5 text-[11px] text-dim">@{prop.alias}</p></div>
			</div>
		</section>
	{/if}
{/snippet}

{#if loading}
	<div class="flex flex-col gap-6">
		<PageHead
			eyebrow="Performance"
			title="Analytics"
			meta="loading closed trades · expectancy, risk &amp; distribution"
		>
			<div class="skeleton h-9 w-56 rounded-control" aria-hidden="true"></div>
		</PageHead>

		{#if $selectedAccountId !== null}
			<div class="card px-5 py-4" aria-hidden="true">
				<div class="grid grid-cols-2 gap-px sm:grid-cols-5">
					{#each Array(5) as _, i (i)}
						<div>
							<div class="skeleton h-2.5 w-16 rounded"></div>
							<div class="skeleton mt-2 h-5 w-20 rounded"></div>
							<div class="skeleton mt-1 h-2.5 w-12 rounded"></div>
						</div>
					{/each}
				</div>
			</div>
		{/if}

		<div aria-hidden="true">
			<AnalyticsSkeleton />
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
	<div class="flex flex-col gap-6" transition:fade={{ duration: 150 }}>
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

		{#if symbolPerf && matrix && confidence}
			<AnalyticsSection title="Edge" meta="by symbol · by setup · confidence" delay={40}>
				<SymbolPerformanceTable data={symbolPerf} />
				<div class="mt-5 border-t border-line pt-5"><SetupMatrix data={matrix} /></div>
				<div class="mt-5 border-t border-line pt-5"><SetupConfidencePanel data={confidence} /></div>
			</AnalyticsSection>
		{/if}

		{#if drawdownAccount && drawdownSetup && ruin}
			<AnalyticsSection title="Risk" meta="drawdown · ruin" delay={80}>
				<DrawdownBreakdown account={drawdownAccount} setup={drawdownSetup} />
				<div class="mt-5 border-t border-line pt-5"><RiskOfRuinPanel data={ruin} /></div>
			</AnalyticsSection>
		{/if}

		<AnalyticsSection title="Curve" meta="equity · underwater" delay={120}>
			<div class="grid grid-cols-1 gap-5 xl:grid-cols-12 xl:gap-0">
				<div class="min-w-0 xl:col-span-8 xl:pr-5">
					<h3 class="eyebrow mb-3">Equity curve</h3>
					{#if points.length > 0}
						<EquityChart {points} />
					{:else}
						<p class="py-10 text-center text-sm text-mut">Not enough data.</p>
					{/if}
				</div>
				<div class="min-w-0 border-t border-line pt-5 xl:col-span-4 xl:border-t-0 xl:border-l xl:pl-5 xl:pt-0">
					<h3 class="eyebrow mb-3">Drawdown</h3>
					{#if points.length > 0}
						<UnderwaterChart {points} />
					{:else}
						<p class="py-10 text-center text-sm text-mut">Not enough data.</p>
					{/if}
				</div>
			</div>
		</AnalyticsSection>

		{#if monthData}
			<MonthlyCalendar
				data={monthData}
				yearDays={days}
				today={tradingToday}
				onPrev={() => void shiftMonth(-1)}
				onNext={() => void shiftMonth(1)}
				onPrevYear={() => void shiftYear(-1)}
				onNextYear={() => void shiftYear(1)}
			/>
		{/if}

		<AnalyticsSection title="Composition" meta="outcome · tags · R" delay={200}>
			<div class="grid grid-cols-1 gap-5 lg:grid-cols-3 lg:gap-0">
				<div class="min-w-0 lg:pr-5">
					<h3 class="eyebrow mb-3">Win / loss / breakeven</h3>
					<OutcomeDonut {summary} />
				</div>
				<div class="min-w-0 border-t border-line pt-5 lg:border-t-0 lg:border-l lg:px-5 lg:pt-0">
					<h3 class="eyebrow mb-3">Tag performance</h3>
					<TagPerformanceBar {tags} />
				</div>
				<div class="min-w-0 border-t border-line pt-5 lg:border-t-0 lg:border-l lg:pl-5 lg:pt-0">
					<h3 class="eyebrow mb-3">R multiple distribution</h3>
					{#if rBuckets.length > 0}
						<RDistributionChart buckets={rBuckets} />
					{:else}
						<p class="py-10 text-center text-sm text-mut">Not enough data.</p>
					{/if}
				</div>
			</div>
		</AnalyticsSection>

		{#if longShort && activity && kpi}
			<AnalyticsSection title="Direction &amp; sessions" meta="long/short · killzones" delay={240}>
				<LongShortOverview {longShort} {activity} />
				<div class="mt-5 border-t border-line pt-5"><SessionGrid {kpi} /></div>
			</AnalyticsSection>
		{/if}

		{#if radarData && activity}
			<AnalyticsSection title="Behavior" meta="weekday · session · streaks" delay={280}>
				<div class="grid grid-cols-1 gap-5 xl:grid-cols-2 xl:gap-0">
					<div class="min-w-0 xl:pr-5"><RadarAnalytics radar={radarData} /></div>
					<div class="min-w-0 border-t border-line pt-5 xl:border-t-0 xl:border-l xl:pl-5 xl:pt-0">
						<StatPanels {activity} />
					</div>
				</div>
			</AnalyticsSection>
		{/if}
	</div>
{/if}

<DayPanel />
<TradeModal />
