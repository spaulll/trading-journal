import type uPlot from 'uplot';

export interface TipContent {
	title: string;
	value: string;
	tone: 'win' | 'loss' | 'be';
}

const TONE_TEXT: Record<TipContent['tone'], string> = {
	win: 'text-emerald-400',
	loss: 'text-rose-400',
	be: 'text-slate-300'
};

/** Floating value tooltip that follows the uPlot cursor on hover. */
export function tooltipPlugin(format: (idx: number) => TipContent | null): uPlot.Plugin {
	let tip: HTMLDivElement | null = null;

	return {
		hooks: {
			init: (u) => {
				u.root.style.position = 'relative';
				tip = document.createElement('div');
				tip.className =
					'pointer-events-none absolute z-10 hidden rounded-lg border border-slate-200 bg-white/95 px-2.5 py-1.5 text-xs shadow-pop backdrop-blur-sm dark:border-white/10 dark:bg-surface-900/95';
				tip.style.transform = 'translate(-50%, -115%)';
				tip.style.whiteSpace = 'nowrap';
				u.root.appendChild(tip);
			},
			setCursor: (u) => {
				if (!tip) return;
				const idx = u.cursor.idx;
				if (idx === null || idx === undefined) {
					tip.style.display = 'none';
					return;
				}
				const content = format(idx);
				if (!content) {
					tip.style.display = 'none';
					return;
				}
				tip.innerHTML =
					`<div class="font-mono text-[10px] tracking-wide text-slate-500 dark:text-slate-400">${content.title}</div>` +
					`<div class="font-mono text-sm font-bold tabular-nums ${TONE_TEXT[content.tone]}">${content.value}</div>`;
				const x = (u.bbox.left ?? 0) + (u.cursor.left ?? 0);
				const y = (u.bbox.top ?? 0) + (u.cursor.top ?? 0);
				tip.style.display = 'block';
				const tw = tip.offsetWidth;
				tip.style.left = `${Math.min(Math.max(x, tw / 2 + 4), Math.max(tw / 2 + 4, u.width - tw / 2 - 4))}px`;
				tip.style.top = `${Math.max(y, 52)}px`;
			},
			destroy: () => {
				tip?.remove();
				tip = null;
			}
		}
	};
}
