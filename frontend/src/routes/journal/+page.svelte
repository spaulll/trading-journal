<script lang="ts">
	import { onMount } from 'svelte';
	import { CalendarPlus } from 'lucide-svelte';
	import PageHead from '$lib/components/PageHead.svelte';
	import StateBlock from '$lib/components/StateBlock.svelte';
	import DayPanel from '$lib/components/DayPanel.svelte';
	import TradeModal from '$lib/components/TradeModal.svelte';
	import { api, type DailyNoteDto } from '$lib/api';
	import { SNAPSHOT_KEYS, readSnapshot, saveSnapshot } from '$lib/offline-snapshot';
	import { markOffline, markOnline, snapshotAt } from '$lib/stores/offline';
	import { loadTrades, trades } from '$lib/stores/trades';
	import { notesVersion, openDay } from '$lib/stores/journal';
	import { dayKeyOf, fmtDate, fmtMoney, pnlTone, toneText } from '$lib/utils/format';

	const BE_TOL = 5.0;

	let notes = $state<DailyNoteDto[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	const todayKey = (() => {
		const d = new Date();
		return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
	})();

	function dayNet(date: string): { count: number; net: number } {
		const closes = $trades.filter(
			(t) => t.status === 'CLOSED' && dayKeyOf(t.timestamp_close ?? t.timestamp_open) === date
		);
		return { count: closes.length, net: closes.reduce((a, t) => a + (t.net_pnl ?? 0), 0) };
	}

	async function refresh(): Promise<void> {
		loading = true;
		error = null;
		try {
			notes = await api.listNotes();
			markOnline();
			const at = saveSnapshot(SNAPSHOT_KEYS.notes, notes);
			if (at) snapshotAt.set(at);
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
		void loadTrades(true);
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
			<article class="card rise p-5" style="animation-delay: {Math.min(ni, 11) * 55}ms" aria-label="Note for {n.date}">
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
					<p class="mt-3 text-[13px] leading-relaxed text-mut"><span class="font-semibold text-fg">Plan:</span> {n.pre_market}</p>
				{/if}
				{#if n.eod_review}
					<p class="mt-2 text-[13px] leading-relaxed whitespace-pre-line text-fg">{n.eod_review}</p>
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
