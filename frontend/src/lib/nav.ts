import { Activity, ArrowLeftRight, Ellipsis, NotebookPen, Receipt, Tags, Wallet } from 'lucide-svelte';

/**
 * Single source of truth for primary navigation (sidebar + mobile tab bar).
 * `mobileLabel` is the compact tab-bar label; `label` stays the full name for
 * the sidebar, tooltip, and accessible name.
 */
export const NAV_LINKS = [
	{ href: '/', label: 'Trades', mobileLabel: 'Trades', icon: ArrowLeftRight },
	{ href: '/analytics', label: 'Analytics', mobileLabel: 'Stats', icon: Activity },
	{ href: '/accounts', label: 'Accounts', mobileLabel: 'Accounts', icon: Wallet },
	{ href: '/prop', label: 'Cash', mobileLabel: 'Cash', icon: Receipt },
	{ href: '/journal', label: 'Journal', mobileLabel: 'Journal', icon: NotebookPen },
	{ href: '/tags', label: 'Tags', mobileLabel: 'Tags', icon: Tags },
	{ href: '/misc', label: 'Misc', mobileLabel: 'Misc', icon: Ellipsis }
] as const;

export function isActiveLink(href: string, pathname: string): boolean {
	return href === '/' ? pathname === '/' : pathname.startsWith(href);
}
