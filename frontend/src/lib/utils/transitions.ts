import { cubicOut } from 'svelte/easing';

/** Shared Svelte transition params — slower, springier easing than default. */

/** Modal drop-in */
export const MODAL = { start: 0.95, duration: 260, easing: cubicOut } as const;

/** Drawer / panel slides */
export const DRAWER = { x: 340, duration: 320, easing: cubicOut } as const;

/** List updates, badges, toasts */
export const FADE = { duration: 220 } as const;

/** Toast entrance */
export const TOAST_IN = { y: 18, duration: 280, easing: cubicOut } as const;
