import { derived, writable } from 'svelte/store';
import { snapshotAgeLabel } from '$lib/offline-snapshot';

/** True when the visible data comes from a local snapshot (server unreachable). */
export const offlineMode = writable(false);

/** ISO timestamp of the snapshot being shown, or null. */
export const snapshotAt = writable<string | null>(null);

export const snapshotLabel = derived(snapshotAt, ($at) =>
	$at
		? `snapshot from ${new Date($at).toLocaleString()} (${snapshotAgeLabel($at)})`
		: 'snapshot of unknown age'
);

export function markOnline(): void {
	offlineMode.set(false);
}

export function markOffline(savedAt: string | null): void {
	snapshotAt.set(savedAt);
	offlineMode.set(true);
}
