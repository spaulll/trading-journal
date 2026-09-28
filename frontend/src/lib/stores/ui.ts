import { browser } from '$app/environment';
import { writable } from 'svelte/store';

const KEY = 'tj-sidebar-collapsed';

function initial(): boolean {
	if (!browser) return false;
	try {
		return localStorage.getItem(KEY) === '1';
	} catch {
		return false;
	}
}

export const sidebarCollapsed = writable<boolean>(initial());

export function toggleSidebar(): void {
	sidebarCollapsed.update((v) => {
		const next = !v;
		if (browser) {
			try {
				localStorage.setItem(KEY, next ? '1' : '0');
			} catch {
				/* private mode — collapse just won't persist */
			}
		}
		return next;
	});
}
