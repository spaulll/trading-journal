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
