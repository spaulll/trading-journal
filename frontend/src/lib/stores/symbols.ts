import { derived, writable } from 'svelte/store';
import { api, errMsg, type SymbolSpecDto } from '$lib/api';

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
