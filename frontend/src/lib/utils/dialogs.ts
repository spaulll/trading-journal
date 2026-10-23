type DialogLayer = {
	element: HTMLElement;
	onEscape: () => void;
};

const layers: DialogLayer[] = [];
let listening = false;

function handleEscape(event: KeyboardEvent): void {
	if (event.key !== 'Escape' || event.defaultPrevented) return;
	const top = layers[layers.length - 1];
	if (!top) return;
	event.preventDefault();
	top.onEscape();
}

/**
 * Register a dialog layer for the duration of an element's life.
 *
 * Escape is handled by one window listener and routed to the topmost layer
 * only, so a drawer does not close when a nested modal or popover is open.
 * Layers are registered in mount order; nested dialogs mount later.
 */
export function dialogEscape(
	element: HTMLElement,
	onEscape: () => void
): { destroy: () => void } {
	const layer: DialogLayer = { element, onEscape };
	layers.push(layer);
	if (!listening) {
		window.addEventListener('keydown', handleEscape);
		listening = true;
	}
	return {
		destroy() {
			const index = layers.indexOf(layer);
			if (index >= 0) layers.splice(index, 1);
			if (layers.length === 0) {
				window.removeEventListener('keydown', handleEscape);
				listening = false;
			}
		}
	};
}
