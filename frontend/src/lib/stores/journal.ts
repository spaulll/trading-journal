import { writable } from 'svelte/store';

/** Calendar/journal day panel date (`YYYY-MM-DD`); null = closed. */
export const selectedDay = writable<string | null>(null);

export function openDay(day: string): void {
	selectedDay.set(day);
}

export function closeDay(): void {
	selectedDay.set(null);
}

/** Bumped on note save/delete so the Journal list refreshes. */
export const notesVersion = writable(0);

export function bumpNotes(): void {
	notesVersion.update((v) => v + 1);
}
