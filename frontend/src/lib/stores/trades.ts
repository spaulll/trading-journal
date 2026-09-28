import { derived, get, writable } from 'svelte/store';
import { errMsg, type ScreenshotDto, type TradeDto, api } from '$lib/api';
import { toasts } from './toast';

export const trades = writable<TradeDto[]>([]);
/** Full server-side count from listAllTrades — masthead uses this, not items.length. */
export const tradesTotal = writable<number>(0);
export const tradesLoading = writable(true);
export const tradesError = writable<string | null>(null);
export const syncing = writable(false);
export const selectedTradeId = writable<number | null>(null);

export const openTrades = derived(trades, ($t) => $t.filter((t) => t.status === 'OPEN'));
export const closedTrades = derived(trades, ($t) => $t.filter((t) => t.status !== 'OPEN'));

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
		const net = trade.net_pnl === null ? 'n/a' : `${trade.net_pnl >= 0 ? '+' : ''}${trade.net_pnl.toFixed(2)}`;
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
 */
export async function loadTrades(quiet = false): Promise<boolean> {
	if (!quiet) {
		tradesLoading.set(true);
		tradesError.set(null);
	}
	try {
		const { items, total } = await api.listAllTrades();
		trades.set(items);
		tradesTotal.set(total);
		if (quiet) tradesError.set(null);
		return true;
	} catch (e) {
		if (!quiet) tradesError.set(errMsg(e));
		return false;
	} finally {
		if (!quiet) tradesLoading.set(false);
	}
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
	if (get(selectedTradeId) === id) selectedTradeId.set(null);
}

export function openTrade(id: number): void {
	selectedTradeId.set(id);
}

export function closeTrade(): void {
	selectedTradeId.set(null);
}
