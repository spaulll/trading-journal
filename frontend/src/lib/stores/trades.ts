import { derived, get, writable } from 'svelte/store';
import { ApiError, api, errMsg, type ScreenshotDto, type TradeDto } from '$lib/api';
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

/** POST sync-bot → toast counts → refresh tables without reload. */
export async function syncFromBot(): Promise<void> {
	if (get(syncing)) return;
	syncing.set(true);
	try {
		const r = await api.syncBot();
		await loadTrades(true);
		const fresh = r.inserted + r.updated;
		toasts.push(
			'success',
			fresh === 0
				? 'Already up to date — no new bot trades.'
				: `Synced ${r.total} trade${r.total === 1 ? '' : 's'} (${r.inserted} new, ${r.updated} updated).`
		);
	} catch (e) {
		const msg = e instanceof ApiError && e.status === 404 ? 'Bot CSV not found on server.' : errMsg(e);
		toasts.push('error', `Sync failed — ${msg}`);
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
