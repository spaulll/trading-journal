import { derived, writable } from 'svelte/store';
import { api, errMsg, type SymbolPreviewDto, type SymbolSpecDto } from '$lib/api';

/**
 * The symbol contract registry, straight from the server.
 *
 * The browser must never guess a contract size — the server prices every
 * trade from this table, so a second copy of the rules in the client would
 * drift and quote a different number.
 */
export const symbols = writable<SymbolSpecDto[]>([]);
export const symbolsError = writable<string | null>(null);

/** Reactive symbol → spec map. */
export const symbolMap = derived(
	symbols,
	($s) => new Map($s.map((x) => [x.symbol.toUpperCase(), x]))
);

let loaded = false;

/** Fetch once per page load; safe to call from any modal. */
export async function loadSymbols(force = false): Promise<void> {
	if (loaded && !force) return;
	loaded = true;
	try {
		symbols.set(await api.listSymbols());
	} catch (e) {
		symbolsError.set(errMsg(e));
	}
}

/** The spec for a typed symbol, or null when it is not registered. */
export function specFor(symbol: string, map: Map<string, SymbolSpecDto>): SymbolSpecDto | null {
	const key = symbol.trim().toUpperCase().replace(/\.$/, '');
	if (!key) return null;
	return map.get(key) ?? null;
}

/**
 * The server's price for one position.
 *
 * The browser asks instead of re-deriving: the preview it shows is then
 * the same number the server stores when the trade closes.
 */
export async function previewSymbol(params: {
	symbol: string;
	direction: string;
	size?: number | null;
	entry?: number | null;
	exit?: number | null;
	sl?: number | null;
	current_sl?: number | null;
}): Promise<SymbolPreviewDto | null> {
	const clean: Record<string, string | number | undefined> = {
		symbol: params.symbol,
		direction: params.direction
	};
	for (const key of ['size', 'entry', 'exit', 'sl', 'current_sl'] as const) {
		const value = params[key];
		if (value !== undefined && value !== null) clean[key] = value;
	}
	try {
		return await api.previewSymbol(clean);
	} catch {
		return null;
	}
}

