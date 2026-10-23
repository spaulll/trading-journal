<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { fade, fly } from 'svelte/transition';
	import { Trash2, X } from 'lucide-svelte';
	import { api, errMsg, type AdherenceDto, type DailyNoteDto } from '$lib/api';
	import { bumpNotes, closeDay, selectedDay } from '$lib/stores/journal';
	import { dayTrades, loadDayTrades, openTrade, openTrades } from '$lib/stores/trades';
	import { toasts } from '$lib/stores/toast';
	import { BE_TOL, fmtDate, fmtMoney, fmtR, pnlTone, rTone, toneText, usdNet } from '$lib/utils/format';
	import { DRAWER, FADE } from '$lib/utils/transitions';
	import { dialogEscape } from '$lib/utils/dialogs';


	const day = $derived($selectedDay);

	/** The day's closes come from the server, bucketed by close day. */
	const closes = $derived(day === null ? [] : $dayTrades);

	/** How the day lined up with the pre-market plan. */
	let adherence = $state<AdherenceDto | null>(null);

	const adherenceTone = $derived.by(() => {
		const score = adherence?.score;
		if (score === null || score === undefined) return 'text-dim';
		if (score >= 80) return 'text-win';
		if (score >= 50) return 'text-flat';
		return 'text-loss';
	});

	async function loadAdherence(forDay: string): Promise<void> {
		try {
			adherence = await api.adherence(forDay);
		} catch {
			adherence = null;
		}
	}

	$effect(() => {
		const wanted = day;
		if (wanted === null) {
			dayTrades.set([]);
			adherence = null;
			return;
		}
		void loadDayTrades(wanted);
		void loadAdherence(wanted);
	});

	/** USD view per close; a trade with no convertible P&L is unpriced. */
	const priced = $derived(
		closes
			.map((t) => ({ t, net: usdNet(t) }))
			.filter((x): x is { t: (typeof closes)[number]; net: number } => x.net !== null)
	);
	const net = $derived(priced.reduce((a, x) => a + x.net, 0));
	const rTotal = $derived(closes.reduce((a, t) => a + (t.r_multiple ?? 0), 0));
	const wins = $derived(priced.filter((x) => x.net > BE_TOL).length);
	const losses = $derived(priced.filter((x) => x.net < -BE_TOL).length);
	const be = $derived(priced.length - wins - losses);
	const unpriced = $derived(closes.length - priced.length);

	let loading = $state(false);
	let saving = $state(false);
	let breachBusy = $state(false);
	// Chained saves. A request that arrives while another is running waits
	// for it instead of being dropped, and the counter keeps the spinner up
	// until the last queued write has landed.
	let noteInFlight: Promise<void> | null = null;
	let noteActive = 0;
	let confirmDelete = $state(false);
	let note = $state<DailyNoteDto | null>(null);
	let preMarket = $state('');
	let eod = $state('');
	let lastDay = $state<string | null>(null);
	let noteState = $state<'idle' | 'saving' | 'saved' | 'error'>('idle');
	let noteHint = $state('');
	let noteTimer: ReturnType<typeof setTimeout> | null = $state(null);
	const NOTE_AUTOSAVE_MS = 900;

	let resizing = $state(false);
	// Custom drawer width in px (null = default `max-w-md`, which is also the minimum).
	let drawerW = $state<number | null>(null);

	const DRAWER_MIN_W = 448; // max-w-md
	const DRAWER_MAX_W = 960;
	const DRAWER_WIDTH_KEY = 'day-drawer-width';

	onMount(() => {
		try {
			const v = Number(localStorage.getItem(DRAWER_WIDTH_KEY));
			if (Number.isFinite(v) && v > DRAWER_MIN_W) {
				drawerW = Math.min(Math.round(v), window.innerWidth);
			}
		} catch {
			// Private mode etc. — fall back to the default width.
		}
	});

	function resetDrawerWidth(): void {
		drawerW = null;
		try {
			localStorage.removeItem(DRAWER_WIDTH_KEY);
		} catch {
			// ignore
		}
	}

	function onGripDown(e: PointerEvent): void {
		(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
		resizing = true;
		e.preventDefault();
	}

	function onGripMove(e: PointerEvent): void {
		if (!resizing) return;
		const vw = window.innerWidth;
		const min = Math.min(DRAWER_MIN_W, vw);
		const max = Math.min(DRAWER_MAX_W, vw);
		const w = Math.round(Math.min(Math.max(vw - e.clientX, min), max));
		// Dragging back to the minimum snaps to the default width.
		drawerW = w <= min + 4 ? null : w;
	}

	function onGripUp(): void {
		if (!resizing) return;
		resizing = false;
		try {
			if (drawerW === null) localStorage.removeItem(DRAWER_WIDTH_KEY);
			else localStorage.setItem(DRAWER_WIDTH_KEY, String(drawerW));
		} catch {
			// ignore
		}
	}

	function noteStamp(): string {
		try {
			return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
		} catch {
			return '';
		}
	}

	onDestroy(() => {
		// The panel is going away. Save whatever the debounce was still
		// holding instead of dropping it — navigating within the debounce
		// window used to lose the note entirely.
		if (noteTimer) {
			clearTimeout(noteTimer);
			noteTimer = null;
			if (dirty) void saveNote(true);
		}
	});

	$effect(() => {
		const key = $selectedDay;
		if (key && key !== lastDay) {
			if (noteTimer) clearTimeout(noteTimer);
			noteTimer = null;
			lastDay = key;
			note = null;
			preMarket = '';
			eod = '';
			confirmDelete = false;
			noteState = 'idle';
			noteHint = '';
			loading = true;
			void api
				.getNote(key)
				.then((n) => {
					if ($selectedDay !== key) return;
					note = n;
					preMarket = n?.pre_market ?? '';
					eod = n?.eod_review ?? '';
				})
				.catch(() => {
					if ($selectedDay === key) toasts.push('error', 'Could not load the day note.');
				})
				.finally(() => {
					if ($selectedDay === key) loading = false;
				});
		}
		if (!key) lastDay = null;
	});

	const dirty = $derived(preMarket !== (note?.pre_market ?? '') || eod !== (note?.eod_review ?? ''));

	function onBackdrop(e: MouseEvent): void {
		if (e.target === e.currentTarget) void flushAndClose();
	}

	/** Flush a pending day-note autosave, then close the panel. */
	async function flushAndClose(): Promise<void> {
		if (noteTimer) {
			clearTimeout(noteTimer);
			noteTimer = null;
		}
		// Await the request already in flight as well — closing the panel
		// mid-flight used to close it with the text still unsaved.
		if (noteInFlight) await noteInFlight.catch(() => {});
		if (dirty) await saveNote(true);
		closeDay();
	}

	function scheduleNoteAutosave(): void {
		if (noteTimer) clearTimeout(noteTimer);
		noteTimer = setTimeout(() => {
			noteTimer = null;
			void saveNote(true);
		}, NOTE_AUTOSAVE_MS);
	}

	async function doSaveNote(quiet: boolean): Promise<void> {
		if (!day) return;
		if (preMarket === (note?.pre_market ?? '') && eod === (note?.eod_review ?? '')) return;
		const key = day;
		noteActive += 1;
		saving = true;
		noteState = 'saving';
		noteHint = '';
		try {
			note = await api.putNote(key, { pre_market: preMarket || null, eod_review: eod || null });
			bumpNotes();
			// The plan just changed, so its score did too.
			void loadAdherence(key);
			noteState = 'saved';
			noteHint = `Saved ${noteStamp()}`;
			if (!quiet) toasts.push('success', 'Day note saved.');
		} catch (err) {
			noteState = 'error';
			noteHint = err instanceof Error ? err.message : 'Save failed';
			toasts.push('error', `Save failed — ${err instanceof Error ? err.message : 'unknown error'}`);
		} finally {
			noteActive -= 1;
			saving = noteActive > 0;
		}
	}

	/**
	 * Queue a day-note save behind whatever is already in flight.
	 *
	 * The old guard returned early when a request was running, so a
	 * keystroke that landed mid-request was dropped with no timer left to
	 * pick it up. Chaining keeps every write and reads the payload when
	 * the request actually runs, so the last one always wins.
	 */
	function saveNote(quiet = false): Promise<void> {
		const run = (noteInFlight ?? Promise.resolve()).then(() => doSaveNote(quiet));
		noteInFlight = run.catch(() => {});
		return run;
	}

	/**
	 * Flag the day as a discipline breach — or clear the flag.
	 *
	 * The bot raises the flag on its own; the trader can also set it from
	 * the drawer, and clear it when the day was read wrongly.
	 */
	async function toggleBreach(): Promise<void> {
		if (!day || breachBusy) return;
		breachBusy = true;
		const next = !(note?.discipline_breach ?? false);
		try {
			if (noteTimer) {
				clearTimeout(noteTimer);
				noteTimer = null;
			}
			if (dirty) await saveNote(true);
			note = await api.putNote(day, { discipline_breach: next });
			bumpNotes();
			void loadAdherence(day);
			toasts.push(
				'success',
				next ? 'Day flagged as a discipline breach.' : 'Discipline breach cleared.'
			);
		} catch (err) {
			toasts.push('error', `Could not update the breach flag — ${errMsg(err)}`);
		} finally {
			breachBusy = false;
		}
	}

	async function doDelete(): Promise<void> {		if (!day) return;
		if (!confirmDelete) {
			confirmDelete = true;
			setTimeout(() => (confirmDelete = false), 4000);
			return;
		}
		try {
			await api.deleteNote(day);
			note = null;
			preMarket = '';
			eod = '';
			confirmDelete = false;
			bumpNotes();
			toasts.push('success', 'Day note deleted.');
		} catch (err) {
			toasts.push('error', `Delete failed — ${err instanceof Error ? err.message : 'unknown error'}`);
		}
	}

	function openTradeFromDay(id: number): void {
		void (async () => {
			if (noteTimer) {
				clearTimeout(noteTimer);
				noteTimer = null;
			}
			if (dirty) await saveNote(true);
			closeDay();
			openTrade(id);
		})();
	}
</script>

{#if day}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<div
		transition:fade={FADE}
		onclick={onBackdrop}
		use:dialogEscape={() => void flushAndClose()}
		tabindex={-1}
		class="fixed inset-0 z-50 bg-base/75 backdrop-blur-[3px]"
		role="dialog"
		aria-modal="true"
		aria-label="Day detail"
	>
		<div
			transition:fly={DRAWER}
			style:width={drawerW === null ? undefined : `${drawerW}px`}
			style:max-width={drawerW === null ? undefined : '100dvw'}
			class="group absolute inset-y-0 right-0 flex w-full max-w-md flex-col border-l border-line bg-panel shadow-pop {resizing
				? 'select-none'
				: ''}"
		>
			<!-- Resize grip (desktop only) — double-click resets to default -->
			<div
				role="separator"
				aria-orientation="vertical"
				aria-label="Resize panel"
				title="Drag to resize · double-click to reset"
				onpointerdown={onGripDown}
				onpointermove={onGripMove}
				onpointerup={onGripUp}
				onpointercancel={onGripUp}
				ondblclick={resetDrawerWidth}
				class="absolute inset-y-0 -left-1.5 z-10 hidden w-3 cursor-ew-resize touch-none sm:block"
			>
				<span
					class="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 transition-opacity duration-150 {resizing
						? 'bg-accent opacity-100'
						: 'bg-accent opacity-0 group-hover:opacity-60'}"
					aria-hidden="true"
				></span>
			</div>
			<div class="flex shrink-0 items-center gap-2 border-b border-line px-5 py-4">
				<span class="num text-lg font-semibold text-fg">{fmtDate(day)}</span>
				{#if note?.discipline_breach}
					<span class="rounded-lg bg-loss/12 px-2 py-0.5 font-mono text-[10px] font-semibold tracking-[0.14em] text-loss uppercase">
						breach
					</span>
				{/if}
				<span class="ml-auto flex shrink-0 items-center gap-2">
					<button
						type="button"
						onclick={() => void toggleBreach()}
						disabled={breachBusy}
						class="rounded-lg border px-2 py-1 font-mono text-[10px] font-bold tracking-[0.12em] uppercase transition-all disabled:opacity-50 {note?.discipline_breach
							? 'border-loss/50 bg-loss/12 text-loss'
							: 'border-line text-dim hover:border-loss/40 hover:text-loss'}"
						aria-pressed={note?.discipline_breach ?? false}
						title="Flag this day as a discipline breach"
					>
						{note?.discipline_breach ? 'Clear breach' : 'Flag breach'}
					</button>
					<button type="button" onclick={() => void flushAndClose()} aria-label="Close" class="btn-icon h-8 w-8">
						<X size={17} strokeWidth={1.8} aria-hidden="true" />
					</button>
				</span>
			</div>

			<div class="no-scrollbar min-h-0 flex-1 overflow-y-auto px-5 py-5">
				<dl class="grid grid-cols-4 gap-x-3 gap-y-4">
					<div>
						<dt class="eyebrow">Net</dt>
						<dd class="num mt-1 text-sm font-semibold {toneText[pnlTone(net)]}">{fmtMoney(net)}</dd>
					</div>
					<div>
						<dt class="eyebrow">R</dt>
						<dd class="num mt-1 text-sm font-semibold {toneText[rTone(rTotal)]}">{fmtR(rTotal)}</dd>
					</div>
					<div>
						<dt class="eyebrow">W·L·BE</dt>
						<dd class="num mt-1 text-sm font-semibold text-fg">{wins}·{losses}·{be}</dd>
					</div>
					<div>
						<dt class="eyebrow">Closed</dt>
						<dd class="num mt-1 text-sm font-semibold text-fg" title={unpriced ? `${unpriced} trade(s) without a USD rate` : undefined}>
							{closes.length}{unpriced ? ` · ${unpriced} n/a` : ''}
						</dd>
					</div>
				</dl>

				{#if adherence}
					<div class="mt-4 rounded-xl border border-line bg-raised/40 px-3 py-2.5">
						<div class="flex items-center gap-2">
							<p class="eyebrow">Plan adherence</p>
							{#if adherence.score !== null}
								<span class="num ml-auto text-sm font-semibold tabular-nums {adherenceTone}">
									{adherence.score.toFixed(0)}/100
								</span>
							{/if}
						</div>
						{#if !adherence.has_plan}
							<p class="num mt-1 text-[12px] text-dim">No pre-market plan for this day.</p>
						{:else}
							<p class="num mt-1 text-[12px] text-dim">
								{#if adherence.planned_setups.length > 0}
									Plan {adherence.planned_setups.map((s) => `#${s}`).join(' ')}
								{/if}
								{#if adherence.traded_setups.length > 0}
									· traded {adherence.traded_setups.map((s) => `#${s}`).join(' ')}
								{/if}
								{#if adherence.planned_size !== null}
									· size {adherence.planned_size}
								{/if}
							</p>
							<ul class="mt-1.5 flex flex-col gap-0.5">
								{#each adherence.notes as n (n)}
									<li class="num text-[11.5px] text-mut">· {n}</li>
								{/each}
							</ul>
						{/if}
					</div>
				{/if}

				{#if closes.length > 0}
					<p class="eyebrow mt-5 mb-2">Trades closed</p>
					<ul class="flex flex-col gap-1.5">
						{#each closes as t, ci (t.id)}
							<li class="anim-fade" style="animation-delay: {ci * 50}ms">
								<button
									type="button"
									onclick={() => openTradeFromDay(t.id)}
									class="flex w-full items-center gap-2 rounded-xl border border-line bg-raised/50 px-3 py-2 text-left transition-colors hover:border-edge"
								>
									<span class="num min-w-0 flex-1 truncate text-[13px] text-fg">
										{(t.direction ?? '').toUpperCase()} {t.symbol ?? '—'}
										<span class="text-dim">· {t.ticket}</span>
									</span>
									<span
										class="num text-[13px] font-semibold {toneText[pnlTone(usdNet(t))]}"
										title={t.quote_currency !== 'USD' && t.net_pnl !== null
											? `Broker: ${t.net_pnl.toLocaleString()} ${t.quote_currency}`
											: undefined}
									>
										{fmtMoney(usdNet(t))}
									</span>
									<span class="num text-[11px] text-dim">{fmtR(t.r_multiple)}</span>
								</button>
							</li>
						{/each}
					</ul>
				{:else}
					<p class="num mt-5 text-[12px] text-dim">No closed trades this day.</p>
				{/if}

				{#if $openTrades.length > 0}
					<p class="eyebrow mt-5 mb-2">Still open</p>
					<ul class="flex flex-col gap-1.5">
						{#each $openTrades as t (t.id)}
							<li>
								<button
									type="button"
									onclick={() => openTradeFromDay(t.id)}
									class="flex w-full items-center gap-2 rounded-xl border border-accent/25 bg-accent/8 px-3 py-2 text-left transition-colors hover:border-accent/50"
								>
									<span class="num min-w-0 flex-1 truncate text-[13px] text-fg">
										{(t.direction ?? '').toUpperCase()} {t.symbol ?? '—'}
										<span class="text-dim">· {t.ticket}</span>
									</span>
								</button>
							</li>
						{/each}
					</ul>
				{/if}

				<div class="mt-6 border-t border-line pt-4">
					<p class="eyebrow mb-2">Day note · <span class="normal-case text-mut">autosaves</span></p>
					{#if loading}
						<div class="skeleton h-20 rounded-xl" aria-hidden="true"></div>
						<div class="skeleton mt-2 h-20 rounded-xl" aria-hidden="true"></div>
					{:else}
						<div class="grid grid-cols-1 gap-3">
							<label class="flex flex-col gap-1.5">
								<span class="eyebrow">Pre-market</span>
								<textarea bind:value={preMarket} oninput={scheduleNoteAutosave} rows={3} placeholder="Plan before the session…" class="field resize-y text-[13px]"></textarea>
							</label>
							<label class="flex flex-col gap-1.5">
								<span class="eyebrow">EOD review</span>
								<textarea bind:value={eod} oninput={scheduleNoteAutosave} rows={4} placeholder="How did the day go? (also settable via the bot's EOD reply)" class="field resize-y text-[13px]"></textarea>
							</label>
						</div>
						<div class="mt-2 flex items-center justify-between gap-2">
							{#if note}
								<button
									type="button"
									onclick={() => void doDelete()}
									class="btn h-8 gap-1.5 px-3 text-[13px] {confirmDelete
										? 'btn-danger shadow-pop'
										: 'text-loss hover:bg-loss/10'}"
								>
									<Trash2 size={14} strokeWidth={1.8} aria-hidden="true" />
									{confirmDelete ? 'Confirm delete?' : 'Delete note'}
								</button>
							{:else}
								<span class="num text-[11px] {noteState === 'error' ? 'text-loss' : 'text-dim'}" aria-live="polite">
									{#if saving || noteState === 'saving'}Saving…{:else if noteState === 'saved'}{noteHint || 'Saved'}{:else if noteState === 'error'}Autosave failed — {noteHint}{:else if dirty}Unsaved changes…{/if}
								</span>
							{/if}
							<span class="flex shrink-0 items-center gap-2">
								{#if note}
									<span class="num text-[11px] {noteState === 'error' ? 'text-loss' : 'text-dim'}" aria-live="polite">
										{#if saving || noteState === 'saving'}Saving…{:else if noteState === 'saved'}{noteHint || 'Saved'}{:else if noteState === 'error'}Autosave failed — {noteHint}{:else if dirty}Unsaved changes…{/if}
									</span>
								{/if}
								<button
									type="button"
									onclick={() => void saveNote(false)}
									disabled={!dirty || saving}
									class="btn btn-ghost h-8 px-3.5 text-[13px]"
								>
									{saving ? 'Saving…' : 'Save now'}
								</button>
							</span>
						</div>
					{/if}
				</div>
			</div>
		</div>
	</div>
{/if}
