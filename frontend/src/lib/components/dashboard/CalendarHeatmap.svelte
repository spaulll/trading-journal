<script lang="ts">
	import { fmtMoney } from '$lib/utils/format';
	import type { CalendarDay } from '$lib/api';

	const { days, year }: { days: CalendarDay[]; year: number } = $props();

	const byDate = $derived(new Map(days.map((d) => [d.date, d])));
	const maxAbs = $derived(Math.max(1, ...days.map((d) => Math.abs(d.net_pnl))));

	interface Cell {
		key: string;
		date: Date | null;
		inYear: boolean;
		pnl: number;
		count: number;
	}

	/** Monday-first week columns covering the full year. */
	function buildWeeks(y: number): Cell[][] {
		const jan1 = new Date(y, 0, 1);
		const mondayOffset = (jan1.getDay() + 6) % 7;
		const start = new Date(y, 0, 1 - mondayOffset);
		const dec31 = new Date(y, 11, 31);
		const weeks: Cell[][] = [];
		const cur = new Date(start);
		while (cur <= dec31 || weeks.length === 0 || weeks[weeks.length - 1].length < 7) {
			const week: Cell[] = [];
			for (let i = 0; i < 7; i++) {
				const iso = `${cur.getFullYear()}-${String(cur.getMonth() + 1).padStart(2, '0')}-${String(cur.getDate()).padStart(2, '0')}`;
				const hit = byDate.get(iso);
				week.push({
					key: iso,
					date: new Date(cur),
					inYear: cur.getFullYear() === y,
					pnl: hit?.net_pnl ?? 0,
					count: hit?.trade_count ?? 0
				});
				cur.setDate(cur.getDate() + 1);
			}
			weeks.push(week);
			if (cur.getFullYear() > y && cur.getDay() === 1) break;
			if (weeks.length > 54) break;
		}
		return weeks;
	}

	const weeks = $derived(buildWeeks(year));

	const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

	function cellClass(cell: Cell): string {
		if (!cell.inYear) return 'bg-transparent';
		if (cell.count === 0) return 'bg-raised';
		if (cell.pnl === 0) return 'bg-flat/40';
		const level = Math.min(4, Math.ceil((Math.abs(cell.pnl) / maxAbs) * 4));
		if (cell.pnl > 0) {
			return (
				['', 'bg-win/25', 'bg-win/45', 'bg-win/70', 'bg-win'][level] +
				' hover:ring-2 hover:ring-accent/60'
			);
		}
		return (
			['', 'bg-loss/25', 'bg-loss/45', 'bg-loss/70', 'bg-loss'][level] +
			' hover:ring-2 hover:ring-accent/60'
		);
	}
</script>

<div class="overflow-x-auto pb-1">
	<div class="w-max">
		<div class="mb-1.5 flex justify-between pl-8 font-mono text-[10px] text-dim" aria-hidden="true">
			{#each MONTHS as month}
				<span>{month}</span>
			{/each}
		</div>
		<div class="flex gap-1">
			<div class="grid shrink-0 grid-rows-7 gap-1 pr-1 font-mono text-[10px] leading-3 tabular-nums text-dim">
				<span class="h-3">M</span><span class="h-3"></span><span class="h-3">W</span><span class="h-3"></span><span class="h-3">F</span><span class="h-3"></span><span class="h-3"></span>
			</div>
			<div class="grid grid-flow-col gap-1" style="grid-template-rows: repeat(7, minmax(0, 1fr));">
				{#each weeks as week}
					{#each week as cell (cell.key)}
						{#if cell.inYear}
							<div class="group relative">
								<div
									class="h-3 w-3 rounded-[3px] transition-all duration-200 {cellClass(cell)}"
									role="img"
									aria-label="{cell.key} · {fmtMoney(cell.pnl)} · {cell.count} trade{cell.count === 1 ? '' : 's'}"
									title="{cell.key} · {fmtMoney(cell.pnl)} · {cell.count} trade{cell.count === 1 ? '' : 's'}"
								></div>
								<div
									class="pointer-events-none absolute bottom-4 left-1/2 z-10 hidden -translate-x-1/2 rounded-lg border border-line bg-panel px-2 py-1 font-mono text-[11px] whitespace-nowrap tabular-nums shadow-pop backdrop-blur-sm group-hover:block"
									aria-hidden="true"
								>
									<span class="text-dim">{cell.key}</span>
									<span class={cell.pnl > 0 ? 'text-win' : cell.pnl < 0 ? 'text-loss' : 'text-flat'}>
										{fmtMoney(cell.pnl)}
									</span>
									<span class="text-dim"> · {cell.count} trade{cell.count === 1 ? '' : 's'}</span>
								</div>
							</div>
						{:else}
							<div class="h-3 w-3"></div>
						{/if}
					{/each}
				{/each}
			</div>
		</div>
	</div>
</div>
