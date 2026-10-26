<script lang="ts">
	import { onMount } from 'svelte';
	import { AlertTriangle, CalendarPlus, Sparkles, X } from 'lucide-svelte';
	import PageHead from '$lib/components/PageHead.svelte';
	import StateBlock from '$lib/components/StateBlock.svelte';
	import DayPanel from '$lib/components/DayPanel.svelte';
	import TradeModal from '$lib/components/TradeModal.svelte';
	import { api, errMsg, type DailyNoteDto, type InsightReportDto, type WeekendReviewResult } from '$lib/api';
	import { SNAPSHOT_KEYS, readSnapshot, saveSnapshot } from '$lib/offline-snapshot';
	import { markOffline, markOnline, snapshotAt } from '$lib/stores/offline';
	import { loadOpenPositions } from '$lib/stores/trades';
	import { notesVersion, openDay } from '$lib/stores/journal';
	import { renderMiniMarkdown } from '$lib/utils/minimd';
	import { fmtDate, fmtMoney, pnlTone, toneText } from '$lib/utils/format';


	let notes = $state<DailyNoteDto[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	/** The day's closed trades, per day — the server's calendar answers this. */
	let calendar = $state<Record<string, { count: number; net: number }>>({});

	// --- Weekend review (LLM summary of errors + strengths) ---
	let reports = $state<InsightReportDto[]>([]);
	let generating = $state(false);
	let reviewResult = $state<WeekendReviewResult | null>(null);
	let reviewError = $state<string | null>(null);
	let overrideFrom = $state('');
	let overrideTo = $state('');
	let expandedReport = $state<number | null>(null);
	let reportsError = $state<string | null>(null);

	/** Last completed Mon–Fri, mirroring the backend default. */
	function defaultWeek(today: Date = new Date()): { from: string; to: string } {
		const wd = (today.getDay() + 6) % 7; // Mon=0
		const monday = new Date(today);
		monday.setDate(today.getDate() - (wd >= 5 ? wd : wd + 7));
		const friday = new Date(monday);
		friday.setDate(monday.getDate() + 4);
		const iso = (d: Date) =>
			`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
		return { from: iso(monday), to: iso(friday) };
	}

	const defaultRange = defaultWeek();
	const defaultLabel = `${fmtDate(defaultRange.from)} – ${fmtDate(defaultRange.to)}`;

	/** A stored review with no body — the old bug: a blank box with no error. */
	const isBlankReport = (markdown: string | null | undefined): boolean =>
		!(markdown ?? '').trim();

	async function loadReports(): Promise<void> {
		try {
			reports = await api.listInsightReports();
			reportsError = null;
		} catch (e) {
			// History is a nice-to-have — never block the page on it, but say so.
			reports = [];
			reportsError = errMsg(e);
		}
	}

	async function generateReview(): Promise<void> {
		if (generating) return;
		if ((overrideFrom && !overrideTo) || (!overrideFrom && overrideTo)) {
			reviewError = 'Pick both a from and a to date, or leave both empty for last week.';
			return;
		}
		generating = true;
		reviewError = null;
		try {
			reviewResult = await api.weekendReview(overrideFrom || undefined, overrideTo || undefined);
			await loadReports();
		} catch (e) {
			reviewError = errMsg(e);
		} finally {
			generating = false;
		}
	}

	async function deleteReport(id: number): Promise<void> {
		try {
			await api.deleteInsightReport(id);
			reports = reports.filter((r) => r.id !== id);
			if (expandedReport === id) expandedReport = null;
			if (reviewResult?.status === 'ok' && reviewResult.report.id === id) reviewResult = null;
		} catch (e) {
			reviewError = errMsg(e);
		}
	}

	const localToday = new Date();
	const localTodayKey = `${localToday.getFullYear()}-${String(localToday.getMonth() + 1).padStart(2, '0')}-${String(localToday.getDate()).padStart(2, '0')}`;
	/** The server's trading day; the local date until the settings load. */
	let serverToday = $state('');
	const todayKey = $derived(serverToday || localTodayKey);

	function dayNet(date: string): { count: number; net: number } {
		return calendar[date] ?? { count: 0, net: 0 };
	}

	/**
	 * The per-day close count and net, straight from the server's calendar.
	 *
	 * The ledger holds one page now, so the journal cannot count the day's
	 * closes from the rows it happens to hold — the calendar already buckets
	 * every trade by close day.
	 */
	async function loadCalendar(days: string[]): Promise<void> {
		const years = [...new Set(days.map((d) => d.slice(0, 4)).filter((y) => /^\d{4}$/.test(y)))];
		const map: Record<string, { count: number; net: number }> = {};
		for (const year of years) {
			try {
				const { days: rows } = await api.calendar(Number(year));
				for (const row of rows) map[row.date] = { count: row.trade_count, net: row.net_pnl };
			} catch {
				// The glance stays empty — the notes are what matter here.
			}
		}
		calendar = map;
	}

	async function refresh(): Promise<void> {
		loading = true;
		error = null;
		try {
			notes = await api.listNotes();
			markOnline();
			const at = saveSnapshot(SNAPSHOT_KEYS.notes, notes);
			if (at) snapshotAt.set(at);
			await loadCalendar(notes.map((n) => n.date));
		} catch (e) {
			const snap = readSnapshot<DailyNoteDto[]>(SNAPSHOT_KEYS.notes);
			if (snap) {
				notes = snap.data;
				markOffline(snap.savedAt);
				error = null;
			} else {
				error = e instanceof Error ? e.message : 'Could not load notes.';
			}
		} finally {
			loading = false;
		}
	}

	onMount(() => {
		void loadOpenPositions();
		void loadReports();
		void api
			.getTradingDay()
			.then((d) => (serverToday = d.today))
			.catch(() => {
				// "Today" falls back to the browser's date.
			});
	});

	$effect(() => {
		$notesVersion;
		void refresh();
	});
</script>

<PageHead eyebrow="journal" title="Journal" meta="{notes.length} days with notes">
	<button type="button" onclick={() => openDay(todayKey)} class="btn btn-primary h-10 px-4 text-sm">
		<CalendarPlus size={16} strokeWidth={2.2} aria-hidden="true" />
		Today
	</button>
</PageHead>

<section aria-label="Weekend review" class="rise mb-5 border-b border-line pb-5">
	<div class="flex flex-wrap items-center gap-2">
		<Sparkles size={16} strokeWidth={2} aria-hidden="true" class="text-accent" />
		<h2 class="text-[15px] font-semibold text-fg">Weekend review</h2>
		<span class="num text-[12px] text-dim">AI summary of errors + strengths · {defaultLabel}</span>
	</div>
	<div class="mt-3 flex flex-wrap items-center gap-2">
		<label class="flex items-center gap-1.5 text-[12px] text-dim">
			<span class="font-mono text-[10px] tracking-[0.14em] uppercase">From</span>
			<input type="date" bind:value={overrideFrom} class="field h-9 px-2 font-mono text-[12px]" aria-label="Review range start" />
		</label>
		<label class="flex items-center gap-1.5 text-[12px] text-dim">
			<span class="font-mono text-[10px] tracking-[0.14em] uppercase">To</span>
			<input type="date" bind:value={overrideTo} class="field h-9 px-2 font-mono text-[12px]" aria-label="Review range end" />
		</label>
		<button
			type="button"
			onclick={() => void generateReview()}
			disabled={generating}
			class="btn btn-ghost h-9 px-4 text-[13px]"
		>
			{generating ? 'Summarizing…' : 'Summarize week'}
		</button>
		{#if generating}
			<span class="text-[12px] text-dim">Reading trade + daily notes…</span>
		{/if}
	</div>

	{#if generating}
		<div class="skeleton card mt-3 h-28" aria-hidden="true"></div>
	{:else if reviewError}
		<p role="alert" class="mt-3 rounded-xl border border-loss/40 bg-loss/8 px-3 py-2 text-[13px] text-loss">
			Summary failed — {reviewError}
		</p>
	{:else if reviewResult?.status === 'empty'}
		<div class="card mt-3 border-dashed px-4 py-6 text-center">
			<p class="text-sm font-medium text-fg">No notes to summarize ({fmtDate(reviewResult.date_from)} – {fmtDate(reviewResult.date_to)})</p>
			<p class="mt-1 text-[13px] text-mut">Write EOD reviews or add trade notes with !mistake tags, then try again.</p>
		</div>
	{:else if reviewResult?.status === 'ok'}
		{#if isBlankReport(reviewResult.report.markdown)}
			<div class="card mt-3 border-dashed px-4 py-6 text-center">
				<p class="text-sm font-medium text-fg">The model returned an empty summary</p>
				<p class="mt-1 text-[13px] text-mut">Nothing was saved — try again.</p>
			</div>
		{:else}
			<article class="mt-3 rounded-xl border border-accent/30 bg-raised/40 px-4 py-3" aria-label="Latest weekend review">
				<p class="num text-[11px] tracking-wide text-dim uppercase">
					{fmtDate(reviewResult.date_from)} – {fmtDate(reviewResult.date_to)} · {reviewResult.report.model}
				</p>
				<div class="prose-review">{@html renderMiniMarkdown(reviewResult.report.markdown)}</div>
			</article>
		{/if}
	{/if}

	{#if reportsError}
		<p role="alert" class="mt-3 rounded-xl border border-loss/40 bg-loss/8 px-3 py-2 text-[13px] text-loss">
			Could not load past reviews — {reportsError}
		</p>
	{/if}

	{#if reports.length > 0}
		<div class="mt-4 border-t border-line pt-3">
			<p class="font-mono text-[10px] tracking-[0.16em] text-dim uppercase">Past reviews ({reports.length})</p>
			<ul class="mt-2 flex flex-col gap-1.5">
				{#each reports as r (r.id)}
					<li class="rounded-lg border border-line">
						<div class="flex items-center gap-1 px-1 py-1">
							<button
								type="button"
								onclick={() => (expandedReport = expandedReport === r.id ? null : r.id)}
								aria-expanded={expandedReport === r.id}
								class="flex min-w-0 flex-1 items-center gap-2 rounded-md px-2 py-1.5 text-left text-[13px] transition-colors hover:bg-raised/50"
							>
								<span class="num truncate font-medium text-fg">{fmtDate(r.date_from)} – {fmtDate(r.date_to)}</span>
								{#if isBlankReport(r.markdown)}
									<span
										class="num shrink-0 rounded-md bg-loss/12 px-1.5 py-0.5 text-[10px] font-semibold tracking-[0.1em] text-loss uppercase"
										title="Saved with no content"
									>
										<AlertTriangle
											size={11}
											strokeWidth={2.4}
											class="inline sm:hidden"
											aria-label="No content"
										/>
										<span class="hidden sm:inline">empty</span>
									</span>
								{/if}
								<span class="num ml-auto hidden shrink-0 text-[11px] text-dim sm:inline">{fmtDate(r.created_at.slice(0, 10))}</span>
							</button>
							<button
								type="button"
								onclick={() => void deleteReport(r.id)}
								aria-label="Delete review {r.date_from} to {r.date_to}"
								class="grid h-7 w-7 shrink-0 place-items-center rounded-md text-dim transition-colors hover:bg-loss/12 hover:text-loss"
							>
								<X size={14} strokeWidth={2.2} aria-hidden="true" />
							</button>
						</div>
						{#if expandedReport === r.id}
							<div class="border-t border-line px-4 py-3">
								{#if isBlankReport(r.markdown)}
									<p class="text-[13px] text-mut">
										This review was saved with no content — generate it again.
									</p>
								{:else}
									<div class="prose-review">{@html renderMiniMarkdown(r.markdown)}</div>
								{/if}
							</div>
						{/if}
					</li>
				{/each}
			</ul>
		</div>
	{/if}
</section>

{#if loading}
	<div class="flex flex-col gap-4">
		<div class="skeleton card h-36" aria-hidden="true"></div>
		<div class="skeleton card h-36" aria-hidden="true"></div>
	</div>
{:else if error}
	<StateBlock kind="error" title="Couldn't load the journal" body={error} actionLabel="Retry" onAction={() => void refresh()} />
{:else if notes.length === 0}
	<StateBlock
		title="No day notes yet"
		body="Reply to the bot's nightly EOD recap, or open any calendar day to write the first note."
		actionLabel="Open today"
		onAction={() => openDay(todayKey)}
	/>
{:else}
	<div class="flex flex-col gap-4">
		{#each notes as n, ni (n.id)}
			{@const glance = dayNet(n.date)}
			<article class="card rise p-4 sm:p-5" style="animation-delay: {Math.min(ni, 11) * 55}ms" aria-label="Note for {n.date}">
				<div class="flex flex-wrap items-center gap-2">
					<h2 class="num text-lg font-semibold text-fg">{fmtDate(n.date)}</h2>
					{#if n.discipline_breach}
						<span class="rounded-lg bg-loss/12 px-2 py-0.5 font-mono text-[10px] font-semibold tracking-[0.14em] text-loss uppercase">
							breach
						</span>
					{/if}
					<span class="num ml-auto text-[12px] text-dim">
						{glance.count} closed · <span class="font-semibold {toneText[pnlTone(glance.net)]}">{fmtMoney(glance.net)}</span>
					</span>
				</div>
				{#if n.pre_market}
					<p class="mt-3 text-[13px] leading-relaxed text-pretty text-mut"><span class="font-semibold text-fg">Plan:</span> {n.pre_market}</p>
				{/if}
				{#if n.eod_review}
					<p class="mt-2 text-[13px] leading-relaxed whitespace-pre-line text-pretty text-fg">{n.eod_review}</p>
				{/if}
				{#if !n.pre_market && !n.eod_review}
					<p class="num mt-2 text-[12px] text-dim">Empty note.</p>
				{/if}
				<div class="mt-3 flex justify-end">
					<button type="button" onclick={() => openDay(n.date)} class="btn btn-ghost h-8 px-3.5 text-[13px]">
						Open day
					</button>
				</div>
			</article>
		{/each}
	</div>
{/if}

<DayPanel />
<TradeModal />
