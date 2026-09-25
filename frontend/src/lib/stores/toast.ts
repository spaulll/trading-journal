import { writable } from 'svelte/store';

export type ToastKind = 'success' | 'error' | 'info';

export interface Toast {
	id: number;
	kind: ToastKind;
	message: string;
}

let nextId = 1;
const TTL = 4500;

function createToasts() {
	const { subscribe, update } = writable<Toast[]>([]);

	function dismiss(id: number): void {
		update((list) => list.filter((t) => t.id !== id));
	}

	function push(kind: ToastKind, message: string): void {
		const id = nextId++;
		update((list) => [...list.slice(-3), { id, kind, message }]);
		setTimeout(() => dismiss(id), TTL);
	}

	return { subscribe, push, dismiss };
}

export const toasts = createToasts();
