import { derived, get, writable } from 'svelte/store';
import { errMsg, type ScreenshotDto, type TradeDto, api } from '$lib/api';
import { toasts } from './toast';

export const trades = writable<TradeDto[]>([]);
export const tradesLoading = writable(true);
export const tradesError = writable<string | null>(null);
export const syncing = writable(false);
export const selectedTradeId = writable<number | null>(null);

export const openTrades = derived(trades, ($t) => $t.filter((t) => t.status === 'OPEN'));
export const closedTrades = derived(trades, ($t) => $t.filter((t) => t.status !== 'OPEN'));

export async function loadTrades(quiet = false): Promise<void> {
	if (!quiet) tradesLoading.set(true);
	tradesError.set(null);
	try {
		trades.set(await api.listTrades());
	} catch (e) {
		tradesError.set(errMsg(e));
	} finally {
		tradesLoading.set(false);
	}
}

/** Reload trades from the API (v1 bot CSV sync retired in PLAN-v2). */
export async function refreshTrades(): Promise<void> {
	if (get(syncing)) return;
	syncing.set(true);
	try {
		await loadTrades(true);
	} catch (e) {
		toasts.push('error', `Refresh failed — ${errMsg(e)}`);
	} finally {
		syncing.set(false);
	}
}

/** Deprecated v1 alias — kept for Header/empty-state compat until Phase 5. */
export const syncFromBot = refreshTrades;

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
