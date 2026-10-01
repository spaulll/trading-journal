<script lang="ts">
	import { fmtMoney } from '$lib/utils/format';
	import type { CalendarDay } from '$lib/api';
	import { openDay } from '$lib/stores/journal';

	const { days, year }: { days: CalendarDay[]; year: number } = $props();

	const byDate = $derived(new Map(days.map((d) => [d.date, d])));
	const maxAbs = $derived(Math.max(1, ...days.map((d) => Math.abs(d.net_pnl))));

	const BE_TOL = 0.01;

	const MONTHS_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
	const WEEKDAYS = ['M', 'T', 'W', 'T', 'F', 'S', 'S']; // Monday-first, matches backend buckets

	const today = new Date();
	const todayKey = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
	const todayMidnight = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();

	interface DayCell {
		blank: false;
		key: string;
		day: number;
		pnl: number;
		count: number;
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
				net += pnl;
				trades += count;
				slots.push({
					blank: false,
					key,
					day: d,
					pnl,
					count,
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

	/** Numbered day tile: tinted background by P&L intensity, number always legible. */
	function tileClass(cell: DayCell): string {
		const base =
			'group relative flex min-h-7 items-center justify-center rounded-md border transition-all duration-150 ease-soft hover:-translate-y-px hover:shadow-card focus-visible:outline-2 focus-visible:outline-accent cursor-pointer sm:min-h-8';
		if (cell.isFuture && cell.count === 0) return `${base} border-line/40 bg-transparent opacity-55`;
		if (cell.count === 0) return `${base} border-line/50 bg-raised/60 hover:border-edge`;
		if (Math.abs(cell.pnl) <= BE_TOL) return `${base} border-flat/25 bg-flat/10 hover:border-flat/50`;
		const lv = level(cell.pnl);
		if (cell.pnl > 0) {
			switch (lv) {
				case 1:
					return `${base} border-win/20 bg-win/10 hover:border-win/45`;
				case 2:
					return `${base} border-win/25 bg-win/25 hover:border-win/55`;
				case 3:
					return `${base} border-win/30 bg-win/50 hover:border-win/70`;
				default:
					return `${base} border-win/40 bg-win/70 hover:border-win`;
			}
		}
		switch (lv) {
			case 1:
				return `${base} border-loss/20 bg-loss/10 hover:border-loss/45`;
			case 2:
				return `${base} border-loss/25 bg-loss/25 hover:border-loss/55`;
			case 3:
				return `${base} border-loss/30 bg-loss/50 hover:border-loss/70`;
			default:
				return `${base} border-loss/40 bg-loss/70 hover:border-loss`;
		}
	}

	function tileNumClass(cell: DayCell): string {
		const base = 'num text-[10px] leading-none tabular-nums sm:text-[11px]';
		if (cell.isToday) return `${base} font-bold text-accent`;
		if (cell.count === 0) return `${base} text-dim/60`;
		if (Math.abs(cell.pnl) <= BE_TOL) return `${base} text-flat`;
		return `${base} font-medium text-fg`;
	}

	function pnlTextClass(pnl: number, count: number): string {
		if (count === 0) return 'text-dim';
		if (pnl > BE_TOL) return 'text-win';
		if (pnl < -BE_TOL) return 'text-loss';
		return 'text-flat';
	}
</script>

<div class="grid grid-cols-2 gap-3 md:grid-cols-3 2xl:grid-cols-4">
	{#each months as month (month.index)}
		<section
			aria-label="{month.label} {year} calendar"
			class="min-w-0 rounded-2xl border border-line bg-raised/40 p-2.5 transition-colors duration-200 hover:border-edge sm:p-3"
		>
			<div class="mb-1.5 flex min-w-0 items-baseline justify-between gap-2">
				<h3 class="shrink-0 text-[12px] font-semibold tracking-tight text-fg sm:text-[13px]">
					{month.label} <span class="font-normal text-dim">{year}</span>
				</h3>
				{#if month.trades > 0}
					<p class="num min-w-0 truncate text-[10px] font-semibold tabular-nums sm:text-[11px] {pnlTextClass(month.net, month.trades)}">
						{fmtMoney(month.net)} <span class="font-normal text-dim">· {month.trades}T</span>
					</p>
				{:else}
					<p class="num shrink-0 text-[10px] text-dim/60 sm:text-[11px]">No trades</p>
				{/if}
			</div>

			<div class="mb-1 grid grid-cols-7 gap-1" aria-hidden="true">
				{#each WEEKDAYS as wd, i (i)}
					<span class="text-center font-mono text-[9px] tracking-[0.1em] text-dim/70">{wd}</span>
				{/each}
			</div>

			<div class="grid grid-cols-7 gap-1" role="grid" aria-label="{month.label} day grid">
				{#each month.slots as slot (slot.key)}
					{#if slot.blank}
						<div aria-hidden="true"></div>
					{:else}
						<button
							type="button"
							onclick={() => openDay(slot.key)}
							aria-label="{slot.key}: {fmtMoney(slot.pnl)}, {slot.count} trade{slot.count === 1 ? '' : 's'} — open day"
							title="{slot.key} · {fmtMoney(slot.pnl)} · {slot.count} trade{slot.count === 1 ? '' : 's'}"
							class="{tileClass(slot)} {slot.isToday ? 'ring-1 ring-accent' : ''}"
						>
							<span class={tileNumClass(slot)}>{slot.day}</span>
							<span
								aria-hidden="true"
								class="pointer-events-none absolute bottom-[calc(100%+6px)] left-1/2 z-30 hidden -translate-x-1/2 rounded-lg border border-line bg-panel px-2 py-1 font-mono text-[11px] whitespace-nowrap tabular-nums shadow-pop backdrop-blur-sm group-hover:block group-focus-visible:block"
							>
								<span class="text-dim">{slot.key}</span>
								<span class={pnlTextClass(slot.pnl, slot.count)}> {fmtMoney(slot.pnl)}</span>
								<span class="text-dim"> · {slot.count} trade{slot.count === 1 ? '' : 's'}</span>
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
			<span class="h-3.5 w-3.5 rounded-[4px] border border-loss/20 bg-loss/10"></span>
			<span class="h-3.5 w-3.5 rounded-[4px] border border-loss/25 bg-loss/25"></span>
			<span class="h-3.5 w-3.5 rounded-[4px] border border-loss/30 bg-loss/50"></span>
			<span class="h-3.5 w-3.5 rounded-[4px] border border-loss/40 bg-loss/70"></span>
		</span>
		<span class="font-mono text-[10px] tracking-wide text-dim uppercase">Max. loss</span>
		{#if maxLoss < 0}
			<span class="num text-[11px] font-semibold text-loss tabular-nums">{fmtMoney(maxLoss)}</span>
		{/if}
	</div>
	<div class="flex items-center gap-2">
		<span class="font-mono text-[10px] tracking-wide text-dim uppercase">Min. profit</span>
		<span class="flex items-center gap-1" aria-hidden="true">
			<span class="h-3.5 w-3.5 rounded-[4px] border border-win/20 bg-win/10"></span>
			<span class="h-3.5 w-3.5 rounded-[4px] border border-win/25 bg-win/25"></span>
			<span class="h-3.5 w-3.5 rounded-[4px] border border-win/30 bg-win/50"></span>
			<span class="h-3.5 w-3.5 rounded-[4px] border border-win/40 bg-win/70"></span>
		</span>
		<span class="font-mono text-[10px] tracking-wide text-dim uppercase">Max. profit</span>
		{#if maxProfit > 0}
			<span class="num text-[11px] font-semibold text-win tabular-nums">{fmtMoney(maxProfit)}</span>
		{/if}
	</div>
	<div class="flex items-center gap-3">
		<span class="flex items-center gap-1.5">
			<span class="h-3.5 w-3.5 rounded-[4px] border border-line/50 bg-raised/60" aria-hidden="true"></span>
			<span class="font-mono text-[10px] tracking-wide text-dim uppercase">No trades</span>
		</span>
		<span class="flex items-center gap-1.5">
			<span class="h-3.5 w-3.5 rounded-[4px] border border-flat/25 bg-flat/10" aria-hidden="true"></span>
			<span class="font-mono text-[10px] tracking-wide text-dim uppercase">Breakeven</span>
		</span>
	</div>
	<p class="num ml-auto hidden text-[11px] text-dim sm:block">Click any day to open its trades</p>
</div>
