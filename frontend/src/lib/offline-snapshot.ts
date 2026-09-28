/** Read-only offline snapshots in localStorage.
 *
 * On every successful fetch the app saves the last-known payload; when the
 * backend is unreachable (power cut, server down) pages restore the snapshot
 * and label it with its age instead of showing an empty error screen.
 * Writes are never queued — the banner says reads-only.
 */

export interface Snapshot<T> {
	savedAt: string;
	data: T;
}

export const SNAPSHOT_KEYS = {
	trades: 'tj-snapshot-trades-v1',
	analytics: 'tj-snapshot-analytics-v1',
	notes: 'tj-snapshot-notes-v1'
} as const;

function storage(): Storage | null {
	try {
		if (typeof localStorage === 'undefined') return null;
		return localStorage;
	} catch {
		return null;
	}
}

export function saveSnapshot<T>(key: string, data: T): string | null {
	const store = storage();
	if (!store) return null;
	try {
		const savedAt = new Date().toISOString();
		store.setItem(key, JSON.stringify({ savedAt, data } satisfies Snapshot<T>));
		return savedAt;
	} catch {
		return null;
	}
}

export function readSnapshot<T>(key: string): Snapshot<T> | null {
	const store = storage();
	if (!store) return null;
	try {
		const raw = store.getItem(key);
		if (!raw) return null;
		const parsed = JSON.parse(raw) as Snapshot<T>;
		if (!parsed || typeof parsed.savedAt !== 'string' || !('data' in parsed)) return null;
		return parsed;
	} catch {
		return null;
	}
}

/** Short human label for snapshot age, e.g. "2h ago". */
export function snapshotAgeLabel(savedAt: string | null): string {
	if (!savedAt) return 'unknown age';
	const ms = Date.now() - new Date(savedAt).getTime();
	if (!Number.isFinite(ms) || ms < 0) return 'just now';
	const mins = Math.floor(ms / 60000);
	if (mins < 1) return 'just now';
	if (mins < 60) return `${mins}m ago`;
	const hours = Math.floor(mins / 60);
	if (hours < 48) return `${hours}h ago`;
	return `${Math.floor(hours / 24)}d ago`;
}
