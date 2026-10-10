import { derived, get, writable } from 'svelte/store';
import { api, errMsg, type AccountDto } from '$lib/api';
import { toasts } from './toast';

export const accounts = writable<AccountDto[]>([]);
export const accountsLoading = writable(true);
export const accountsError = writable<string | null>(null);
export const selectedAccountId = writable<number | null>(null);
try {
	const v = localStorage.getItem('selected-account-id');
	if (v) selectedAccountId.set(Number(v));
} catch {
	// ignore
}
selectedAccountId.subscribe((v) => {
	try {
		if (v === null) localStorage.removeItem('selected-account-id');
		else localStorage.setItem('selected-account-id', String(v));
	} catch {
		// ignore
	}
});

export const selectedAccount = derived([accounts, selectedAccountId], ([$a, $id]) =>
	$id === null ? null : ($a.find((x) => x.id === $id) ?? null)
);

/** Reactive id → alias map for ledger chips (plain aliasOf() is not reactive). */
export const accountMap = derived(accounts, ($a) => new Map($a.map((x) => [x.id, x.alias])));

export function chipAlias(map: Map<number, string>, id: number | null | undefined): string {
	if (id === null || id === undefined) return 'unassigned';
	return map.get(id) ?? `#${id}`;
}

export async function loadAccounts(): Promise<void> {
	accountsLoading.set(true);
	accountsError.set(null);
	try {
		accounts.set(await api.listAccounts());
	} catch (e) {
		accountsError.set(errMsg(e));
	} finally {
		accountsLoading.set(false);
	}
}

export async function createAccount(payload: Record<string, unknown>): Promise<AccountDto | null> {
	try {
		const acc = await api.createAccount(payload);
		accounts.update((l) => [...l, acc].sort((a, b) => a.alias.localeCompare(b.alias)));
		toasts.push('success', `Account @${acc.alias} created.`);
		return acc;
	} catch (e) {
		toasts.push('error', `Create failed — ${errMsg(e)}`);
		return null;
	}
}

export async function saveAccount(id: number, patch: Record<string, unknown>): Promise<boolean> {
	try {
		const acc = await api.updateAccount(id, patch);
		accounts.update((l) => l.map((x) => (x.id === id ? acc : x)));
		toasts.push('success', `Account @${acc.alias} updated.`);
		return true;
	} catch (e) {
		toasts.push('error', `Update failed — ${errMsg(e)}`);
		return false;
	}
}

export function aliasOf(id: number | null | undefined): string {
	if (id === null || id === undefined) return 'unassigned';
	return get(accounts).find((a) => a.id === id)?.alias ?? `#${id}`;
}
