import { writable } from 'svelte/store';
import { api } from '$lib/api';

export const connected = writable<boolean | null>(null);

let timer: ReturnType<typeof setInterval> | null = null;

export async function checkConnection(): Promise<void> {
	try {
		await api.health();
		connected.set(true);
	} catch {
		connected.set(false);
	}
}

export function startPolling(): void {
	if (timer) return;
	void checkConnection();
	timer = setInterval(() => void checkConnection(), 30000);
}
