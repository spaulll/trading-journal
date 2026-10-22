import { derived, writable } from 'svelte/store';

/** The ledger's filter state — one definition, shared by the table, the summary and the export. */
export type LedgerStatus = 'ALL' | 'OPEN' | 'CLOSED';
export type LedgerSort = 'newest' | 'oldest' | 'net-desc' | 'net-asc' | 'r-desc';

export interface LedgerFilters {
	status: LedgerStatus;
	/** Free text: a symbol or a ticket. */
	query: string;
	/** A tag name, with or without the #/! prefix. */
	tag: string;
	/** '' (every account), 'unassigned', or an account id. */
	account: string;
	/** Open-day bounds, YYYY-MM-DD. */
	dateFrom: string;
	dateTo: string;
	sort: LedgerSort;
}

const INITIAL: LedgerFilters = {
	status: 'ALL',
	query: '',
	tag: '',
	account: '',
	dateFrom: '',
	dateTo: '',
	sort: 'newest'
};

/** The saved account scope is where the ledger starts. */
function savedAccount(): string {
	try {
		return localStorage.getItem('selected-account-id') ?? '';
	} catch {
		return '';
	}
}

export const ledgerFilters = writable<LedgerFilters>({ ...INITIAL, account: savedAccount() });

/** The ledger's pagination — the browser asks for one page at a time. */
export interface LedgerPage {
	page: number;
	pageSize: number;
}

export const ledgerPage = writable<LedgerPage>({ page: 1, pageSize: 50 });

/**
 * The server query for a filter set — the one place the wire format lives.
 *
 * The list, the id list, the summary and the CSV export all send this, so
 * a filter can never mean one thing in the table and another in the export.
 */
export function buildLedgerQuery(
	filters: LedgerFilters,
	account: string,
	extra: Record<string, string | number | undefined> = {}
): string {
	const qs = new URLSearchParams();
	if (filters.status !== 'ALL') qs.set('status', filters.status);
	const query = filters.query.trim();
	if (query) qs.set('q', query);
	const tag = filters.tag.trim();
	if (tag) qs.set('tag', tag);
	if (account === 'unassigned') qs.set('unassigned', 'true');
	else if (account) qs.set('account_id', account);
	if (filters.dateFrom) qs.set('date_from', `${filters.dateFrom}T00:00:00`);
	if (filters.dateTo) qs.set('date_to', `${filters.dateTo}T23:59:59`);
	if (filters.sort !== 'newest') qs.set('sort', filters.sort);
	for (const [key, value] of Object.entries(extra)) {
		if (value === undefined || value === '') continue;
		qs.set(key, String(value));
	}
	const text = qs.toString();
	return text ? `?${text}` : '';
}

/** The query the ledger's own request uses. */
export const ledgerQuery = derived(
	[ledgerFilters, ledgerPage],
	([$f, $p]) => buildLedgerQuery($f, $f.account, { page: $p.page, page_size: $p.pageSize })
);

/** True when the ledger is showing something narrower than the whole history. */
export const ledgerHasFilter = derived(
	ledgerFilters,
	($f) =>
		$f.status !== 'ALL' ||
		$f.query.trim() !== '' ||
		$f.tag.trim() !== '' ||
		$f.account !== '' ||
		$f.dateFrom !== '' ||
		$f.dateTo !== ''
);

/** Merge a filter change into the ledger state. A new filter starts at page one. */
export function setLedgerFilters(patch: Partial<LedgerFilters>): void {
	ledgerFilters.update(($f) => ({ ...$f, ...patch }));
	ledgerPage.update(($p) => ({ ...$p, page: 1 }));
}

/**
 * Set the account scope on its own.
 *
 * The saved account is read on mount, not chosen by the user, so it must not
 * send the ledger back to page one — that would drop the page the reader is
 * on every time the table re-mounts.
 */
export function setLedgerAccount(account: string): void {
	ledgerFilters.update(($f) => ($f.account === account ? $f : { ...$f, account }));
}

/** Back to the unfiltered ledger. */
export function resetLedgerFilters(): void {
	ledgerFilters.set({ ...INITIAL });
	ledgerPage.update(($p) => ({ ...$p, page: 1 }));
}

/** Jump to a page — the pager never asks for a page that does not exist. */
export function gotoPage(page: number, pages: number): void {
	ledgerPage.update(($p) => ({ ...$p, page: Math.min(Math.max(1, Math.round(page)), Math.max(1, pages)) }));
}

/** Change how many rows one page holds. A new size starts at page one. */
export function setPageSize(size: number): void {
	ledgerPage.update(($p) => ({ ...$p, pageSize: Math.max(1, Math.round(size)), page: 1 }));
}

/** How many pages the filtered ledger has. */
export function pageCount(total: number, pageSize: number): number {
	return Math.max(1, Math.ceil(total / Math.max(1, pageSize)));
}
