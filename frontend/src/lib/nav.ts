import { Activity, ArrowLeftRight, NotebookPen } from 'lucide-svelte';

/** Single source of truth for primary navigation (top bar + mobile tab bar). */
export const NAV_LINKS = [
	{ href: '/', label: 'Trades', icon: ArrowLeftRight },
	{ href: '/analytics', label: 'Analytics', icon: Activity },
	{ href: '/journal', label: 'Journal', icon: NotebookPen }
] as const;

export function isActiveLink(href: string, pathname: string): boolean {
	return href === '/' ? pathname === '/' : pathname.startsWith(href);
}
