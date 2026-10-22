import { get, writable } from 'svelte/store';
import { errMsg, type ScreenshotDto, type TradeDto, api } from '$lib/api';
import { SNAPSHOT_KEYS, readSnapshot, saveSnapshot } from '$lib/offline-snapshot';
import { usdNet } from '$lib/utils/format';
import { ledgerQuery } from './ledger';
import { markOffline, markOnline, snapshotAt } from './offline';
import { toasts } from './toast';

export const trades = writable<TradeDto[]>([]);
/** Server-side count of the filtered ledger — the masthead uses this, not items.length. */
export const tradesTotal = writable<number>(0);
/** How many trades each status tab holds under the current filter. */
export const tradeCounts = writable<{ ALL: number; OPEN: number; CLOSED: number }>({
	ALL: 0,
	OPEN: 0,
	CLOSED: 0
});
/** The page the ledger is on. */
export const tradesPage = writable(1);
/** How many rows one page holds. */
export const tradesPageSize = writable(50);
export const tradesLoading = writable(true);
export const tradesError = writable<string | null>(null);
export const syncing = writable(false);
export const selectedTradeId = writable<number | null>(null);

/** The open positions, fetched on their own — the ledger holds one filtered page. */
export const openTrades = writable<TradeDto[]>([]);
/** The closed trades of the day the journal drawer is showing. */
export const dayTrades = writable<TradeDto[]>([]);
/** Every trade the client has seen — the drawer opens a trade by id. */
export const tradeCache = writable<Map<number, TradeDto>>(new Map());

/** Interactive lifecycle modal state (Phase 5). */
export type LifecycleModal = { kind: 'open' } | { kind: 'close'; tradeId: number };
export const lifecycleModal = writable<LifecycleModal | null>(null);
export const lifecycleBusy = writable(false);

export function requestOpen(): void {
	lifecycleModal.set({ kind: 'open' });
}

export function requestClose(tradeId: number): void {
	selectedTradeId.set(null);
	lifecycleModal.set({ kind: 'close', tradeId });
}

export function dismissLifecycle(): void {
	if (!get(lifecycleBusy)) lifecycleModal.set(null);
}

export async function submitOpen(payload: Record<string, unknown>): Promise<boolean> {
	lifecycleBusy.set(true);
	try {
		const trade = await api.openTrade(payload);
		upsertTrade(trade);
		lifecycleModal.set(null);
		toasts.push('success', `Opened ${(trade.direction ?? '').toUpperCase()} ${trade.symbol ?? ''} (${trade.ticket}).`);
		return true;
	} catch (e) {
		toasts.push('error', `Open failed — ${errMsg(e)}`);
		return false;
	} finally {
		lifecycleBusy.set(false);
	}
}

export async function submitClose(tradeId: number, payload: Record<string, unknown>): Promise<boolean> {	lifecycleBusy.set(true);
	try {
		const trade = await api.closeTrade(tradeId, payload);
		upsertTrade(trade);
		lifecycleModal.set(null);
		const usd = usdNet(trade);
		const net = usd === null ? 'n/a' : `${usd >= 0 ? '+' : ''}$${usd.toFixed(2)}`;
		toasts.push('success', `Closed ${trade.symbol ?? ''} ${net} (${trade.r_multiple === null ? 'n/a' : `${trade.r_multiple.toFixed(2)}R`}).`);
		return true;
	} catch (e) {
		toasts.push('error', `Close failed — ${errMsg(e)}`);
		return false;
	} finally {
		lifecycleBusy.set(false);
	}
}

export async function submitBackfill(record: Record<string, unknown>): Promise<boolean> {
	lifecycleBusy.set(true);
	try {
		const r = await api.backfill(record);
		lifecycleModal.set(null);
		await loadTrades(true);
		if (r.inserted.length > 0) {
			toasts.push('success', `Backfilled ${r.inserted.length} trade${r.inserted.length === 1 ? '' : 's'} (${r.inserted[0]}${r.inserted.length > 1 ? ', …' : ''}).`);
		} else {
			toasts.push('success', 'Nothing new — record already exists.');
		}
		return true;
	} catch (e) {
		toasts.push('error', `Backfill failed — ${errMsg(e)}`);
		return false;
	} finally {
		lifecycleBusy.set(false);
	}
}

/**
 * Returns `false` when the API could not be reached, so callers can surface it.
 * Quiet (background) refreshes never clobber the visible list on failure — the
 * previous data stays on screen and the caller reports the miss instead.
 *
 * The query is the ledger's filter state, so the browser asks the server for
 * one page of the rows it is going to show instead of downloading the whole
 * history and filtering it here.
 */
export async function loadTrades(quiet = false, query: string = get(ledgerQuery)): Promise<boolean> {
	if (!quiet) {
		tradesLoading.set(true);
		tradesError.set(null);
	}
	try {
		const { items, total, page, page_size, counts } = await api.listTradesPaged(query);
		trades.set(items);
		tradesTotal.set(total);
		tradesPage.set(page);
		tradesPageSize.set(page_size);
		tradeCounts.set(counts ?? { ALL: total, OPEN: 0, CLOSED: 0 });
		cacheTrades(items);
		if (quiet) tradesError.set(null);
		markOnline();
		snapshotAt.set(saveSnapshot(SNAPSHOT_KEYS.trades, { items, total }) ?? null);
		return true;
	} catch (e) {
		// Server unreachable: fall back to the last labelled snapshot so the
		// journal stays readable during outages (read-only, see banner).
		const snap = readSnapshot<{ items: TradeDto[]; total: number }>(SNAPSHOT_KEYS.trades);
		if (snap) {
			trades.set(snap.data.items);
			tradesTotal.set(snap.data.total);
			tradesError.set(null);
			markOffline(snap.savedAt);
			return true;
		}
		if (!quiet) tradesError.set(errMsg(e));
		return false;
	} finally {
		if (!quiet) tradesLoading.set(false);
	}
}

/**
 * The open positions, on their own query.
 *
 * The ledger shows one filtered page, so the live positions cannot come out
 * of it — an open trade may sit on a later page, or outside the filter.
 */
export async function loadOpenPositions(): Promise<void> {
	try {
		const { items } = await api.listTradesPaged('?status=OPEN&page_size=200');
		openTrades.set(items);
		cacheTrades(items);
	} catch {
		// The live list is best-effort: keep whatever is on screen.
	}
}

/** The closed trades of one day — the journal drawer's own query. */
export async function loadDayTrades(day: string): Promise<void> {
	try {
		const { items } = await api.listTradesPaged(
			`?status=CLOSED&closed_from=${day}T00:00:00&closed_to=${day}T23:59:59&page_size=200`
		);
		dayTrades.set(items);
		cacheTrades(items);
	} catch {
		dayTrades.set([]);
	}
}

/** Fetch a trade the client has not seen — the drawer opens one by id. */
export async function ensureTrade(id: number): Promise<void> {
	if (get(tradeCache).has(id)) return;
	try {
		const trade = await api.getTrade(id);
		cacheTrades([trade]);
	} catch {
		// Nothing to show — the drawer keeps what it has.
	}
}

/** Remember the trades the client has seen, so a drawer can find them later. */
function cacheTrades(list: TradeDto[]): void {
	if (list.length === 0) return;
	tradeCache.update((cache) => {
		const next = new Map(cache);
		for (const trade of list) next.set(trade.id, trade);
		return next;
	});
}

/** Reload trades from the API (v1 bot CSV sync retired in PLAN-v2). */
export async function refreshTrades(): Promise<void> {
	if (get(syncing)) return;
	syncing.set(true);
	try {
		const ok = await loadTrades(true);
		if (!ok) toasts.push('error', `Refresh failed — ${get(tradesError) ?? 'API unreachable'}`);
	} finally {
		syncing.set(false);
	}
}

export function upsertTrade(trade: TradeDto): void {
	trades.update((list) => {
		const i = list.findIndex((t) => t.id === trade.id);
		if (i === -1) return [trade, ...list];
		const next = [...list];
		next[i] = trade;
		return next;
	});
	cacheTrades([trade]);
}

export function appendScreenshot(tradeId: number, shot: ScreenshotDto): void {
	trades.update((list) =>
		list.map((t) => (t.id === tradeId ? { ...t, screenshots: [...t.screenshots, shot] } : t))
	);
}

export function updateScreenshot(tradeId: number, shot: ScreenshotDto): void {
	trades.update((list) =>
		list.map((t) =>
			t.id === tradeId
				? { ...t, screenshots: t.screenshots.map((s) => (s.id === shot.id ? shot : s)) }
				: t
		)
	);
}

export function removeTrade(id: number): void {
	trades.update((list) => list.filter((t) => t.id !== id));
	tradeCache.update((cache) => {
		const next = new Map(cache);
		next.delete(id);
		return next;
	});
	if (get(selectedTradeId) === id) selectedTradeId.set(null);
}

export function openTrade(id: number): void {
	selectedTradeId.set(id);
}

export function closeTrade(): void {
	selectedTradeId.set(null);
}
