/**
 * Fluid-height action: keeps the host box glued to its content height and
 * glides (`height` transition) whenever that height changes — tab switches,
 * month navigation, async chart mounts, sidebar collapse, viewport resizes.
 *
 * The host must have exactly one element child wrapping the content (e.g. a
 * keyed panel div); anything inside may change freely. Overflow stays
 * visible so floating tooltips are never clipped. No-op under
 * `prefers-reduced-motion`.
 *
 * Usage: <div use:fluidHeight>{#key tab}<div>…</div>{/key}</div>
 */
export interface FluidHeightParams {
	duration?: number;
}

export function fluidHeight(
	node: HTMLElement,
	params: FluidHeightParams = {}
): { destroy: () => void } {
	const reduced =
		typeof window !== 'undefined' &&
		!!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
	if (reduced) return { destroy() {} };

	const duration = params.duration ?? 380;
	const EASE = 'cubic-bezier(0.22, 1, 0.36, 1)';

	let inner: HTMLElement | null = null;
	let lastH = 0;
	let raf = 0;

	const lock = (h: number, animate: boolean): void => {
		node.style.transition = animate ? `height ${duration}ms ${EASE}` : 'none';
		node.style.height = `${h}px`;
		lastH = h;
	};

	const track = (el: HTMLElement | null): void => {
		if (el === inner) return;
		if (inner) ro.unobserve(inner);
		inner = el;
		if (inner) ro.observe(inner);
	};

	const settle = (animate: boolean): void => {
		cancelAnimationFrame(raf);
		raf = requestAnimationFrame(() => {
			track(node.firstElementChild as HTMLElement | null);
			if (!inner) return;
			const next = inner.offsetHeight;
			if (next === lastH) return;
			if (!animate) {
				lock(next, false);
				return;
			}
			// Restart from the current box so the glide starts exactly where
			// the eye is, then ease to the new content height.
			lock(lastH, false);
			void node.offsetHeight;
			lock(next, true);
		});
	};

	const ro = new ResizeObserver(() => settle(true));
	// Child swaps (keyed panels remount the inner wrapper) re-target tracking.
	const mo = new MutationObserver(() => settle(true));
	mo.observe(node, { childList: true });

	// Lock the natural height without animating, then follow content.
	lastH = node.offsetHeight;
	node.style.height = `${lastH}px`;
	track(node.firstElementChild as HTMLElement | null);
	if (inner) ro.observe(inner);

	return {
		destroy() {
			cancelAnimationFrame(raf);
			ro.disconnect();
			mo.disconnect();
			node.style.height = '';
			node.style.transition = '';
		}
	};
}
/**
 * Count-up action: animates a number inside `node`, rendering each frame with
 * the supplied formatter. Mounts with a 0 → value sweep, re-sweeps when the
 * bound value actually changes, and snaps instantly under
 * `prefers-reduced-motion`.
 *
 * Usage: <span use:countup={{ value: n, format: (v) => fmtMoney(v) }}>
 */
export interface CountUpParams {
	value: number;
	format: (v: number) => string;
	duration?: number;
}

const easeOutExpo = (t: number): number => (t >= 1 ? 1 : 1 - Math.pow(2, -10 * t));

export function countup(
	node: HTMLElement,
	params: CountUpParams
): { update: (p: CountUpParams) => void; destroy: () => void } {
	let frame = 0;
	let target = params.value;
	let from = 0;
	let current = 0;
	let startedAt = 0;

	const reduced =
		typeof window !== 'undefined' &&
		!!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

	const paint = (v: number): void => {
		node.textContent = params.format(v);
	};

	const tick = (now: number): void => {
		const t = Math.min(1, (now - startedAt) / (params.duration ?? 900));
		current = from + (target - from) * easeOutExpo(t);
		paint(current);
		if (t < 1) frame = requestAnimationFrame(tick);
		else {
			current = target;
			paint(current);
		}
	};

	const start = (): void => {
		if (reduced) {
			current = target;
			paint(current);
			return;
		}
		cancelAnimationFrame(frame);
		startedAt = performance.now();
		frame = requestAnimationFrame(tick);
	};

	start();

	return {
		update(next: CountUpParams) {
			const changed = next.value !== target;
			params = next;
			if (!changed) {
				// Formatter may have changed (e.g. $ ↔ % toggle) — repaint.
				paint(current);
				return;
			}
			target = next.value;
			if (reduced) {
				current = target;
				paint(current);
				return;
			}
			from = current;
			start();
		},
		destroy() {
			cancelAnimationFrame(frame);
		}
	};
}
