import { writable } from 'svelte/store';
import { api } from '$lib/api';

/** Calibrated broker clock: null = not set (time inputs stay UTC). */
export const brokerOffset = writable<{ minutes: number; label: string } | null>(null);

let loaded = false;

/** Fetch once per page load; safe to call from any modal. */
export async function loadBrokerOffset(): Promise<void> {
	if (loaded) return;
	loaded = true;
	try {
		const r = await api.getBrokerOffset();
		if (r.offset_minutes !== null) {
			brokerOffset.set({ minutes: r.offset_minutes, label: r.label ?? '' });
		}
	} catch {
		// Offline backend — inputs stay in UTC mode.
	}
}
