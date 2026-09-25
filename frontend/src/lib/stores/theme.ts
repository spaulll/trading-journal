import { browser } from '$app/environment';
import { writable } from 'svelte/store';

export type Theme = 'dark' | 'light';
const KEY = 'tj-theme';

function initial(): Theme {
	if (!browser) return 'dark';
	try {
		return localStorage.getItem(KEY) === 'light' ? 'light' : 'dark';
	} catch {
		return 'dark';
	}
}

export const theme = writable<Theme>(initial());

export function applyTheme(t: Theme): void {
	if (!browser) return;
	document.documentElement.classList.toggle('dark', t === 'dark');
	try {
		localStorage.setItem(KEY, t);
	} catch {
		/* private mode — theme just won't persist */
	}
}

export function toggleTheme(): void {
	theme.update((t) => {
		const next: Theme = t === 'dark' ? 'light' : 'dark';
		applyTheme(next);
		return next;
	});
}

if (browser) {
	applyTheme(initial());
	theme.subscribe(applyTheme);
}
