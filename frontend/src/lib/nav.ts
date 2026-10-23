import { Activity, ArrowLeftRight, Ellipsis, NotebookPen, Receipt, Tags, Wallet } from 'lucide-svelte';

/** Single source of truth for primary navigation (top bar + mobile tab bar). */
export const NAV_LINKS = [
	{ href: '/', label: 'Trades', icon: ArrowLeftRight },
	{ href: '/analytics', label: 'Analytics', icon: Activity },
	{ href: '/accounts', label: 'Accounts', icon: Wallet },
	{ href: '/prop', label: 'Cash', icon: Receipt },
	{ href: '/journal', label: 'Journal', icon: NotebookPen },
	{ href: '/tags', label: 'Tags', icon: Tags },
	{ href: '/misc', label: 'Misc', icon: Ellipsis }
] as const;

export function isActiveLink(href: string, pathname: string): boolean {
	return href === '/' ? pathname === '/' : pathname.startsWith(href);
}
