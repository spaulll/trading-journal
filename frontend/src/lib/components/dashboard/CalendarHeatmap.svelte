<script lang="ts">
	import { BE_TOL, fmtMoney } from '$lib/utils/format';
	import type { CalendarDay } from '$lib/api';
	import { openDay, selectedDay } from '$lib/stores/journal';

	const { days, year, today = '' }: { days: CalendarDay[]; year: number; today?: string } = $props();

	const byDate = $derived(new Map(days.map((d) => [d.date, d])));
	const maxAbs = $derived(Math.max(1, ...days.map((d) => Math.abs(d.net_pnl))));

	const MONTHS_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
	const WEEKDAYS = ['M', 'T', 'W', 'T', 'F', 'S', 'S']; // Monday-first, matches backend buckets

	const localToday = new Date();
	const localTodayKey = `${localToday.getFullYear()}-${String(localToday.getMonth() + 1).padStart(2, '0')}-${String(localToday.getDate()).padStart(2, '0')}`;
	const todayKey = $derived(today || localTodayKey);
	const todayMidnight = new Date(localToday.getFullYear(), localToday.getMonth(), localToday.getDate()).getTime();

	interface DayCell {
		blank: false;
		key: string;
		day: number;
		pnl: number;
		count: number;
		unpriced: number;
		isToday: boolean;
		isFuture: boolean;
	}

	type Slot = { blank: true; key: string } | DayCell;

	interface MonthBlock {
		index: number;
		label: string;
		net: number;
		trades: number;
		slots: Slot[];
	}

	const months = $derived.by((): MonthBlock[] => {
		const out: MonthBlock[] = [];
		for (let m = 0; m < 12; m++) {
			const first = new Date(year, m, 1);
			const lead = (first.getDay() + 6) % 7; // Monday-first offset
			const dim = new Date(year, m + 1, 0).getDate();
			const slots: Slot[] = [];
			for (let i = 0; i < lead; i++) slots.push({ blank: true, key: `${year}-${m}-lead-${i}` });
			let net = 0;
			let trades = 0;
			for (let d = 1; d <= dim; d++) {
				const key = `${year}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
				const hit = byDate.get(key);
				const pnl = hit?.net_pnl ?? 0;
				const count = hit?.trade_count ?? 0;
				const unpriced = hit?.unpriced ?? 0;
				net += pnl;
				trades += count;
				slots.push({
					blank: false,
					key,
					day: d,
					pnl,
					count,
					unpriced,
					isToday: key === todayKey,
					isFuture: new Date(year, m, d).getTime() > todayMidnight
				});
			}
			while (slots.length % 7 !== 0) slots.push({ blank: true, key: `${year}-${m}-trail-${slots.length}` });
			out.push({ index: m, label: MONTHS_SHORT[m], net, trades, slots });
		}
		return out;
	});

	const maxProfit = $derived(days.reduce((a, d) => Math.max(a, d.net_pnl), 0));
	const maxLoss = $derived(days.reduce((a, d) => Math.min(a, d.net_pnl), 0));

	function level(pnl: number): number {
		return Math.min(4, Math.max(1, Math.ceil((Math.abs(pnl) / maxAbs) * 4)));
	}

	/** Small filled squares (no day numbers): tinted background by P&L intensity. */
	function tileClass(cell: DayCell): string {
		const base =
			'group relative aspect-square w-full rounded-[3px] border transition-[transform,background-color,border-color,box-shadow] duration-150 ease-soft hover:scale-110 hover:border-edge hover:shadow-card hover:z-10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent cursor-pointer';
		if (cell.isFuture && cell.count === 0) return `${base} border-line-soft bg-transparent opacity-40`;
		if (cell.count === 0) return `${base} border-line-soft bg-raised/60`;
		if (cell.unpriced > 0 && cell.unpriced >= cell.count)
			return `${base} border-dashed border-dim/50 bg-raised/60`;
		if (Math.abs(cell.pnl) <= BE_TOL) return `${base} border-flat/30 bg-flat/15`;
		const lv = level(cell.pnl);
		if (cell.pnl > 0) {
			switch (lv) {
				case 1:
					return `${base} border-win/20 bg-win/10`;
				case 2:
					return `${base} border-win/25 bg-win/25`;
				case 3:
					return `${base} border-win/30 bg-win/50`;
				default:
					return `${base} border-win/40 bg-win/70`;
			}
		}
		switch (lv) {
			case 1:
				return `${base} border-loss/20 bg-loss/10`;
			case 2:
				return `${base} border-loss/25 bg-loss/25`;
			case 3:
				return `${base} border-loss/30 bg-loss/50`;
			default:
				return `${base} border-loss/40 bg-loss/70`;
		}
	}

	/** A full-width hairline at the foot of every traded day; empty days stay bare. */
	function barClass(cell: DayCell): string {
		if (cell.count === 0) return '';
		if (cell.unpriced > 0 && cell.unpriced >= cell.count) return 'bg-dim';
		if (Math.abs(cell.pnl) <= BE_TOL) return 'bg-flat';
		return cell.pnl > 0 ? 'bg-win' : 'bg-loss';
	}

	function pnlTextClass(pnl: number, count: number, unpriced = 0): string {
		if (count === 0 || (unpriced > 0 && unpriced >= count)) return 'text-dim';
		if (pnl > BE_TOL) return 'text-win';
		if (pnl < -BE_TOL) return 'text-loss';
		return 'text-flat';
	}

	function tooltipAlign(col: number): string {
		if (col <= 1) return 'left-0';
		if (col >= 5) return 'right-0';
		return 'left-1/2 -translate-x-1/2';
	}
</script>

<div class="grid grid-cols-2 gap-1.5 sm:grid-cols-4 sm:gap-2 xl:grid-cols-6">
	{#each months as month, mi (month.index)}
		<section
			aria-label="{month.label} {year} calendar"
			class="rise min-w-0 rounded-xl border border-line bg-raised/40 p-1.5 transition-colors duration-200 hover:border-edge sm:p-2"
			style="animation-delay: {mi * 45}ms"
		>
			<div class="mb-1 flex min-w-0 items-baseline justify-between gap-1">
				<h3 class="shrink-0 text-[10px] font-semibold tracking-tight text-fg sm:text-[11px]">
					{month.label} <span class="font-normal text-dim">{year}</span>
				</h3>
				{#if month.trades > 0}
					<p class="num min-w-0 truncate text-[9px] font-semibold tabular-nums sm:text-[10px] {pnlTextClass(month.net, month.trades)}">
						{fmtMoney(month.net)}
					</p>
				{/if}
			</div>

			<div class="mb-0.5 grid grid-cols-7 gap-[3px]" aria-hidden="true">
				{#each WEEKDAYS as wd, i (i)}
					<span class="text-center font-mono text-[8px] tracking-[0.08em] text-dim/70 sm:text-[9px]">{wd}</span>
				{/each}
			</div>

			<div class="grid grid-cols-7 gap-[3px]" role="grid" aria-label="{month.label} day grid">
				{#each month.slots as slot, si (slot.key)}
					{#if slot.blank}
						<div class="aspect-square w-full" aria-hidden="true"></div>
					{:else}
						{@const isSelected = $selectedDay === slot.key}
						<button
							type="button"
							onclick={() => openDay(slot.key)}
							aria-label="{slot.key}: {fmtMoney(slot.pnl)}, {slot.count} trade{slot.count === 1 ? '' : 's'}{slot.unpriced > 0 ? `, ${slot.unpriced} unpriced` : ''} — open day"
							aria-current={slot.isToday ? 'date' : undefined}
							title="{slot.key} · {fmtMoney(slot.pnl)} · {slot.count} trade{slot.count === 1 ? '' : 's'}"
							class="anim-tile {tileClass(slot)} {slot.isToday ? 'ring-2 ring-accent shadow-glow z-10' : ''} {isSelected ? 'outline outline-2 outline-offset-1 outline-fg z-20' : ''}"
							style="animation-delay: {Math.min(mi * 45 + si * 4, 650)}ms"
						>
							{#if slot.count > 0}
								<span class="absolute inset-x-0 bottom-0 h-0.5 rounded-b-sm {barClass(slot)}" aria-hidden="true"></span>
							{/if}
							<span
								aria-hidden="true"
								class="pointer-events-none absolute bottom-[calc(100%+6px)] z-30 hidden flex-col gap-0.5 rounded-control border border-edge bg-overlay p-2 whitespace-nowrap group-hover:flex group-focus-visible:flex {tooltipAlign(si % 7)}"
							>
								<span class="font-mono text-2xs font-medium tracking-wide text-dim">{slot.key}</span>
								<span class="font-mono text-xs font-semibold tabular-nums {pnlTextClass(slot.pnl, slot.count, slot.unpriced)}">
									{fmtMoney(slot.pnl)}
								</span>
								<span class="font-mono text-2xs tabular-nums text-dim">
									{slot.count} trade{slot.count === 1 ? '' : 's'}{slot.unpriced > 0 ? ` · ${slot.unpriced} unpriced` : ''}
								</span>
							</span>
						</button>
					{/if}
				{/each}
			</div>
		</section>
	{/each}
</div>

<div class="mt-4 flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-line pt-3" aria-label="Heatmap legend">
	<div class="flex items-center gap-2">
		<span class="font-mono text-[10px] tracking-wide text-dim uppercase">Min. loss</span>
		<span class="flex items-center gap-1" aria-hidden="true">
			<span class="relative h-3.5 w-3.5 overflow-hidden rounded-[4px] border border-loss/20 bg-loss/10"><span class="absolute inset-x-0 bottom-0 h-0.5 bg-loss"></span></span>
			<span class="relative h-3.5 w-3.5 overflow-hidden rounded-[4px] border border-loss/25 bg-loss/25"><span class="absolute inset-x-0 bottom-0 h-0.5 bg-loss"></span></span>
			<span class="relative h-3.5 w-3.5 overflow-hidden rounded-[4px] border border-loss/30 bg-loss/50"><span class="absolute inset-x-0 bottom-0 h-0.5 bg-loss"></span></span>
			<span class="relative h-3.5 w-3.5 overflow-hidden rounded-[4px] border border-loss/40 bg-loss/70"><span class="absolute inset-x-0 bottom-0 h-0.5 bg-loss"></span></span>
		</span>
		<span class="font-mono text-[10px] tracking-wide text-dim uppercase">Max. loss</span>
		{#if maxLoss < 0}
			<span class="num text-[11px] font-semibold text-loss tabular-nums">{fmtMoney(maxLoss)}</span>
		{/if}
	</div>
	<div class="flex items-center gap-2">
		<span class="font-mono text-[10px] tracking-wide text-dim uppercase">Min. profit</span>
		<span class="flex items-center gap-1" aria-hidden="true">
			<span class="relative h-3.5 w-3.5 overflow-hidden rounded-[4px] border border-win/20 bg-win/10"><span class="absolute inset-x-0 bottom-0 h-0.5 bg-win"></span></span>
			<span class="relative h-3.5 w-3.5 overflow-hidden rounded-[4px] border border-win/25 bg-win/25"><span class="absolute inset-x-0 bottom-0 h-0.5 bg-win"></span></span>
			<span class="relative h-3.5 w-3.5 overflow-hidden rounded-[4px] border border-win/30 bg-win/50"><span class="absolute inset-x-0 bottom-0 h-0.5 bg-win"></span></span>
			<span class="relative h-3.5 w-3.5 overflow-hidden rounded-[4px] border border-win/40 bg-win/70"><span class="absolute inset-x-0 bottom-0 h-0.5 bg-win"></span></span>
		</span>
		<span class="font-mono text-[10px] tracking-wide text-dim uppercase">Max. profit</span>
		{#if maxProfit > 0}
			<span class="num text-[11px] font-semibold text-win tabular-nums">{fmtMoney(maxProfit)}</span>
		{/if}
	</div>
	<div class="flex items-center gap-3">
		<span class="flex items-center gap-1.5">
			<span class="h-3.5 w-3.5 rounded-[4px] border border-line-soft bg-raised/60" aria-hidden="true"></span>
			<span class="font-mono text-[10px] tracking-wide text-dim uppercase">No trades</span>
		</span>
		<span class="flex items-center gap-1.5">
			<span class="relative h-3.5 w-3.5 overflow-hidden rounded-[4px] border border-flat/25 bg-flat/10"><span class="absolute inset-x-0 bottom-0 h-0.5 bg-flat"></span></span>
			<span class="font-mono text-[10px] tracking-wide text-dim uppercase">Breakeven</span>
		</span>
		<span class="flex items-center gap-1.5">
			<span class="relative h-3.5 w-3.5 overflow-hidden rounded-[4px] border border-dashed border-dim/40 bg-raised/60"><span class="absolute inset-x-0 bottom-0 h-0.5 bg-dim"></span></span>
			<span class="font-mono text-[10px] tracking-wide text-dim uppercase">Unpriced</span>
		</span>
	</div>
	<p class="num ml-auto hidden text-[11px] text-dim sm:block">Click any day to open its trades</p>
</div>
