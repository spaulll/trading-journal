import { writable } from 'svelte/store';

/** Calendar/journal day panel date (`YYYY-MM-DD`); null = closed. */
export const selectedDay = writable<string | null>(null);

export function openDay(day: string): void {
	selectedDay.set(day);
}

export function closeDay(): void {
	selectedDay.set(null);
}
