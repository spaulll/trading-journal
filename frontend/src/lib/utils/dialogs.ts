type DialogLayer = {
	element: HTMLElement;
	onEscape: () => void;
};

const FOCUSABLE_SELECTOR = [
	'a[href]',
	'button:not([disabled])',
	'input:not([disabled]):not([type="hidden"])',
	'select:not([disabled])',
	'textarea:not([disabled])',
	'[tabindex]:not([tabindex="-1"])'
].join(',');

const layers: DialogLayer[] = [];
let listening = false;

function focusableElements(element: HTMLElement): HTMLElement[] {
	return Array.from(element.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
		(candidate) =>
			candidate.getClientRects().length > 0 &&
			candidate.getAttribute('aria-hidden') !== 'true'
	);
}

function handleKeydown(event: KeyboardEvent): void {
	if (event.defaultPrevented) return;
	const top = layers[layers.length - 1];
	if (!top) return;

	if (event.key === 'Escape') {
		event.preventDefault();
		top.onEscape();
		return;
	}

	if (event.key !== 'Tab') return;

	const focusables = focusableElements(top.element);
	if (focusables.length === 0) {
		event.preventDefault();
		top.element.focus({ preventScroll: true });
		return;
	}

	const first = focusables[0];
	const last = focusables[focusables.length - 1];
	const active = document.activeElement;

	if (!top.element.contains(active)) {
		event.preventDefault();
		(event.shiftKey ? last : first).focus({ preventScroll: true });
		return;
	}

	if (event.shiftKey && (active === first || active === top.element)) {
		event.preventDefault();
		last.focus({ preventScroll: true });
	} else if (!event.shiftKey && active === last) {
		event.preventDefault();
		first.focus({ preventScroll: true });
	}
}

/**
 * Register a dialog layer for the duration of an element's life.
 *
 * Escape is handled by one window listener and routed to the topmost layer
 * only, so a drawer does not close when a nested modal or popover is open.
 * The layer also receives focus on mount, traps Tab inside its element, and
 * restores focus to the trigger when it is destroyed. Layers are registered
 * in mount order; nested dialogs mount later.
 */
export function dialogLayer(
	element: HTMLElement,
	onEscape: () => void
): { destroy: () => void } {
	const previousFocus =
		document.activeElement instanceof HTMLElement ? document.activeElement : null;
	if (!element.hasAttribute('tabindex')) element.tabIndex = -1;

	const layer: DialogLayer = { element, onEscape };
	layers.push(layer);
	if (!listening) {
		window.addEventListener('keydown', handleKeydown);
		listening = true;
	}

	element.focus({ preventScroll: true });

	return {
		destroy() {
			const index = layers.indexOf(layer);
			if (index >= 0) layers.splice(index, 1);
			if (layers.length === 0) {
				window.removeEventListener('keydown', handleKeydown);
				listening = false;
			}
			if (previousFocus?.isConnected) previousFocus.focus({ preventScroll: true });
		}
	};
}
