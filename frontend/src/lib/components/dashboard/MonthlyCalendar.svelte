<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { Chart, registerables } from 'chart.js';
	import type { CalendarDay, MonthlyCalendarDto } from '$lib/api';
	import CalendarHeatmap from '$lib/components/dashboard/CalendarHeatmap.svelte';
	import { fmtMoney } from '$lib/utils/format';

	Chart.register(...registerables);
	Chart.defaults.color = '#94a3b8';
	Chart.defaults.borderColor = 'rgba(148,163,184,0.12)';
	Chart.defaults.font.family = 'Inter, sans-serif';

	const {
		data,
		yearDays,
		onPrev,
		onNext
	}: {
		data: MonthlyCalendarDto;
		yearDays: CalendarDay[];
		onPrev: () => void;
		onNext: () => void;
	} = $props();

	const MONTHS = [
		'January', 'February', 'March', 'April', 'May', 'June',
		'July', 'August', 'September', 'October', 'November', 'December'
	];

	let unit = $state<'usd' | 'pct'>('usd');
	let tab = $state<'month' | 'year'>('month');

	const monthNet = $derived(data.weeks.reduce((a, w) => a + w.net_pnl, 0));
	const todayKey = `${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, '0')}-${String(new Date().getDate()).padStart(2, '0')}`;

	const cells = $derived.by(() => {
		const first = new Date(data.year, data.month - 1, 1);
		const lead = (first.getDay() + 6) % 7; // Monday-first offset
		const dim = new Date(data.year, data.month, 0).getDate();
		const out: ({ blank: true } | { blank: false; key: string; day: number })[] = [];
		for (let i = 0; i < lead; i++) out.push({ blank: true });
		for (let d = 1; d <= dim; d++) {
			const key = `${data.year}-${String(data.month).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
			out.push({ blank: false, key, day: d });
		}
		while (out.length % 7 !== 0) out.push({ blank: true });
		return out;
	});

	function fmtCellMoney(net: number): string {
		const abs = Math.abs(net);
		const body = abs.toLocaleString('en-US', {
			style: 'currency',
			currency: 'USD',
			minimumFractionDigits: 0,
			maximumFractionDigits: Number.isInteger(abs) ? 0 : 2
		});
		return (net > 0 ? '+' : '') + body;
	}

	function dayValue(net: number): string {
		if (unit === 'usd') return fmtCellMoney(net);
		if (monthNet === 0) return '0.0%';
		const pct = (net / Math.abs(monthNet)) * 100;
		return `${pct > 0 ? '+' : ''}${pct.toFixed(1)}%`;
	}

	function cellClass(outcome: string, isToday: boolean): string {
		const base = 'min-w-0 overflow-hidden min-h-16 rounded-lg border p-1 text-left transition-colors sm:min-h-20 sm:p-2';
		const ring = isToday ? ' ring-1 ring-emerald-500' : '';
		switch (outcome) {
			case 'win':
				return `${base} bg-emerald-50 border-emerald-200 dark:bg-[#122e26] dark:border-emerald-500/30${ring}`;
			case 'loss':
				return `${base} bg-rose-50 border-rose-200 dark:bg-[#36171a] dark:border-rose-500/30${ring}`;
			case 'be':
				return `${base} bg-slate-100 border-slate-200 dark:bg-white/[0.03] dark:border-white/10${ring}`;
			default:
				return `${base} bg-slate-50/60 border-slate-100 dark:bg-white/[0.015] dark:border-white/[0.05]${ring}`;
		}
	}

	const valueClass = (net: number, count: number): string =>
		count === 0
			? 'text-slate-400 dark:text-slate-600'
			: net > 0
				? 'text-emerald-700 dark:text-emerald-400'
				: net < 0
					? 'text-rose-700 dark:text-rose-400'
					: 'text-slate-500 dark:text-slate-400';

	let donut = $state<HTMLCanvasElement | null>(null);
	let chart: Chart | null = null;

	function renderDonut(): void {
		if (!donut) return;
		chart?.destroy();
		chart = new Chart(donut, {
			type: 'doughnut',
			data: {
				labels: ['Winning days', 'Losing days', 'Breakeven'],
				datasets: [
					{
						data: [data.outcome.wins, data.outcome.losses, data.outcome.breakeven],
						backgroundColor: ['#10b981', '#ef4444', '#64748b'],
						borderWidth: 0,
						hoverOffset: 4
					}
				]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				cutout: '72%',
				plugins: { legend: { position: 'bottom', labels: { boxWidth: 9, padding: 10 } } }
			}
		});
	}

	onMount(() => {
		renderDonut();
		return () => {
			chart?.destroy();
			chart = null;
		};
	});

	$effect(() => {
		[data.outcome.wins, data.outcome.losses, data.outcome.breakeven].join(',');
		if (donut) renderDonut();
	});

	onDestroy(() => {
		chart?.destroy();
		chart = null;
	});

	const card =
		'rounded-xl border border-slate-200 bg-white p-4 shadow-card dark:border-white/[0.07] dark:bg-surface-900';
	const navBtn =
		'grid h-7 w-7 place-items-center rounded-md border border-slate-200 text-slate-500 transition-all duration-150 hover:text-slate-900 focus-visible:outline-emerald-500 active:scale-95 dark:border-white/10 dark:text-slate-400 dark:hover:text-white';
	const toggleBtn = (active: boolean): string =>
		`rounded-md px-2.5 py-1 font-mono text-xs tabular-nums transition-colors ${active ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300' : 'text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200'}`;
</script>

<section class={card} aria-label="Monthly trading calendar">
	<div class="mb-3 flex flex-wrap items-center gap-2">
		<div class="flex items-center gap-1">
			<button type="button" onclick={onPrev} aria-label="Previous month" class={navBtn}>‹</button>
			<h2 class="min-w-36 text-center text-[13px] font-semibold tracking-tight">
				{MONTHS[data.month - 1]} {data.year}
			</h2>
			<button type="button" onclick={onNext} aria-label="Next month" class={navBtn}>›</button>
		</div>
		<div class="ml-auto flex items-center gap-1">
			<div class="flex rounded-lg border border-slate-200 p-0.5 dark:border-white/10" role="tablist" aria-label="Calendar view">
				<button type="button" role="tab" aria-selected={tab === 'month'} class={toggleBtn(tab === 'month')} onclick={() => (tab = 'month')}>Month</button>
				<button type="button" role="tab" aria-selected={tab === 'year'} class={toggleBtn(tab === 'year')} onclick={() => (tab = 'year')}>Year</button>
			</div>
			{#if tab === 'month'}
				<div class="flex rounded-lg border border-slate-200 p-0.5 dark:border-white/10" aria-label="Value unit">
					<button type="button" class={toggleBtn(unit === 'usd')} onclick={() => (unit = 'usd')}>$</button>
					<button type="button" class={toggleBtn(unit === 'pct')} onclick={() => (unit = 'pct')}>%</button>
				</div>
			{/if}
		</div>
	</div>

	{#if tab === 'year'}
		<CalendarHeatmap days={yearDays} year={data.year} />
	{:else}
		<div class="grid grid-cols-1 gap-4 xl:grid-cols-4">
			<div class="xl:col-span-3">
				<div class="mb-2 grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-5">
					{#each data.weeks as w}
						<div class="rounded-lg border border-slate-200 px-2.5 py-1.5 dark:border-white/[0.07] dark:bg-white/[0.02]">
							<p class="font-mono text-[10px] tracking-wide text-slate-500 uppercase tabular-nums dark:text-slate-500">{w.label}</p>
							<p class="font-mono text-sm font-semibold tabular-nums {valueClass(w.net_pnl, w.trade_count)}">
								{unit === 'usd' ? fmtMoney(w.net_pnl) : dayValue(w.net_pnl)}
							</p>
							<p class="font-mono text-[10px] text-slate-500 tabular-nums dark:text-slate-500">{w.trade_count} trades</p>
						</div>
					{/each}
				</div>

				<div class="grid grid-cols-7 gap-1 sm:gap-1.5" role="grid" aria-label="{MONTHS[data.month - 1]} day grid">
					{#each ['M', 'T', 'W', 'T', 'F', 'S', 'S'] as d}
						<p class="pb-1 text-center font-mono text-[10px] text-slate-400 tabular-nums dark:text-slate-600">{d}</p>
					{/each}
					{#each cells as c}
						{#if c.blank}
							<div></div>
						{:else}
							{@const info = data.days[c.key] ?? { net_pnl: 0, trade_count: 0, outcome: 'inactive' }}
							<div role="gridcell" class={cellClass(info.outcome, c.key === todayKey)} title="{c.key}: {fmtMoney(info.net_pnl)} · {info.trade_count} trades">
								<p class="font-mono text-[10px] leading-none tabular-nums {c.key === todayKey ? 'font-bold text-emerald-600 dark:text-emerald-400' : 'text-slate-500 dark:text-slate-500'}">
									{c.day}
								</p>
								{#if info.trade_count > 0}
									<p class="mt-1 truncate font-mono text-[10px] leading-tight font-semibold tabular-nums sm:text-xs {valueClass(info.net_pnl, info.trade_count)}">
										{dayValue(info.net_pnl)}
									</p>
									<p class="font-mono text-[9px] leading-tight text-slate-500 tabular-nums dark:text-slate-500">
										{info.trade_count}T
									</p>
								{/if}
							</div>
						{/if}
					{/each}
				</div>
			</div>

			<aside class="flex flex-col gap-3" aria-label="Month summary">
				<div class="h-44"><canvas bind:this={donut}></canvas></div>
				<div class="grid grid-cols-2 gap-2">
					<div class="rounded-lg border border-slate-200 p-2.5 dark:border-white/[0.07] dark:bg-white/[0.02]">
						<p class="text-[11px] text-slate-500 dark:text-slate-400">Trading Days</p>
						<p class="font-mono text-lg font-bold tabular-nums">{data.summary.trading_days}</p>
					</div>
					<div class="rounded-lg border border-slate-200 p-2.5 dark:border-white/[0.07] dark:bg-white/[0.02]">
						<p class="text-[11px] text-slate-500 dark:text-slate-400">Day Win Rate</p>
						<p class="font-mono text-lg font-bold tabular-nums">{data.summary.day_win_rate.toFixed(1)}%</p>
					</div>
					<div class="rounded-lg border border-slate-200 p-2.5 dark:border-emerald-500/20 dark:bg-emerald-500/[0.04]">
						<p class="text-[11px] text-slate-500 dark:text-slate-400">Winning Days</p>
						<p class="font-mono text-lg font-bold text-emerald-600 tabular-nums dark:text-emerald-400">{data.summary.winning_days}</p>
					</div>
					<div class="rounded-lg border border-slate-200 p-2.5 dark:border-rose-500/20 dark:bg-rose-500/[0.04]">
						<p class="text-[11px] text-slate-500 dark:text-slate-400">Losing Days</p>
						<p class="font-mono text-lg font-bold text-rose-600 tabular-nums dark:text-rose-400">{data.summary.losing_days}</p>
					</div>
				</div>
			</aside>
		</div>
	{/if}
</section>
