import { cubicOut } from 'svelte/easing';

/** Shared Svelte transition params (PLAN Task 3.1). Tailwind handles the rest. */

/** Modal drop-in */
export const MODAL = { start: 0.96, duration: 200, easing: cubicOut } as const;

/** Drawer / panel slides */
export const DRAWER = { x: 300, duration: 250, easing: cubicOut } as const;

/** List updates, badges, toasts */
export const FADE = { duration: 150 } as const;

/** Toast entrance */
export const TOAST_IN = { y: 12, duration: 200, easing: cubicOut } as const;
