<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { Chart, registerables } from 'chart.js';
	import type { CalendarDay, MonthlyCalendarDto } from '$lib/api';
	import CalendarHeatmap from '$lib/components/dashboard/CalendarHeatmap.svelte';
	import { fmtMoney } from '$lib/utils/format';
	import { openDay } from '$lib/stores/journal';
	import { palette } from '$lib/utils/palette';
	import { theme } from '$lib/stores/theme';
	import SegControl from '$lib/components/SegControl.svelte';
	import { fly } from 'svelte/transition';
	import { TAB } from '$lib/utils/transitions';
	import { countup, fluidHeight } from '$lib/utils/motion';

	Chart.register(...registerables);

	const {
		data,
		yearDays,
		onPrev,
		onNext,
		onPrevYear,
		onNextYear
	}: {
		data: MonthlyCalendarDto;
		yearDays: CalendarDay[];
		onPrev: () => void;
		onNext: () => void;
		onPrevYear: () => void;
		onNextYear: () => void;
	} = $props();

	const MONTHS = [
		'January', 'February', 'March', 'April', 'May', 'June',
		'July', 'August', 'September', 'October', 'November', 'December'
	];

	let unit = $state<'usd' | 'pct'>('usd');
	let tab = $state<'month' | 'year'>('month');

	// Shared BE rule with backend BE_TOLERANCE (|net| <= 0.01 → breakeven).
	const BE_TOL = 0.01;

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

	/** Below `sm` the day cell is ~41px wide: drop the currency symbol and the
	 *  cents so the P&L stays readable instead of ellipsing mid-number. */
	function compactValue(net: number): string {
		if (unit === 'usd') {
			const body = Math.round(Math.abs(net)).toLocaleString('en-US');
			return (net > 0 ? '+' : net < 0 ? '-' : '') + body;
		}
		if (monthNet === 0) return '0%';
		const pct = (net / Math.abs(monthNet)) * 100;
		return `${pct > 0 ? '+' : ''}${Math.round(pct)}%`;
	}

	function dayValue(net: number): string {
		if (unit === 'usd') return fmtCellMoney(net);
		if (monthNet === 0) return '0.0%';
		const pct = (net / Math.abs(monthNet)) * 100;
		return `${pct > 0 ? '+' : ''}${pct.toFixed(1)}%`;
	}

	function cellClass(outcome: string, isToday: boolean): string {
		const base =
			'min-h-16 min-w-0 overflow-hidden rounded-xl border p-1.5 text-left transition-all duration-200 ease-spring hover:-translate-y-0.5 sm:min-h-20 sm:p-2';
		const ring = isToday ? ' ring-1 ring-accent shadow-glow' : '';
		switch (outcome) {
			case 'win':
				return `${base} border-win/25 bg-win/10${ring}`;
			case 'loss':
				return `${base} border-loss/25 bg-loss/10${ring}`;
			case 'be':
				return `${base} border-flat/25 bg-flat/10${ring}`;
			default:
				return `${base} border-line bg-raised${ring}`;
		}
	}

	const valueClass = (net: number, count: number): string =>
		count === 0
			? 'text-dim'
			: net > BE_TOL
				? 'text-win'
				: net < -BE_TOL
					? 'text-loss'
					: 'text-flat';

	let donut = $state<HTMLCanvasElement | null>(null);
	let chart: Chart | null = null;
	let yearPie = $state<HTMLCanvasElement | null>(null);
	let yearPieChart: Chart | null = null;

	// Yearly outcome summary (Year tab): day-level wins/losses/BE derived from
	// yearDays with the shared BE rule. Mirrors the monthly outcome donut so
	// Month ↔ Year stay consistent.
	const yearOutcome = $derived.by(() => {
		let wins = 0,
			losses = 0,
			be = 0,
			net = 0;
		for (const d of yearDays) {
			if ((d.trade_count ?? 0) === 0) continue;
			net += d.net_pnl ?? 0;
			if ((d.net_pnl ?? 0) > BE_TOL) wins++;
			else if ((d.net_pnl ?? 0) < -BE_TOL) losses++;
			else be++;
		}
		const days = wins + losses + be;
		return { wins, losses, breakeven: be, days, net, winRate: days ? (wins / days) * 100 : 0 };
	});

	function renderDonut(): void {
		if (!donut) return;
		const p = palette();
		Chart.defaults.color = p.axis;
		Chart.defaults.borderColor = p.grid;
		Chart.defaults.font.family = 'Geist, ui-sans-serif, sans-serif';
		chart?.destroy();
		chart = new Chart(donut, {
			type: 'doughnut',
			data: {
				labels: ['Winning days', 'Losing days', 'Breakeven'],
				datasets: [
					{
						data: [data.outcome.wins, data.outcome.losses, data.outcome.breakeven],
						backgroundColor: [p.win, p.loss, p.flat],
						borderColor: p.panel,
						borderWidth: 3,
						hoverOffset: 8
					}
				]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				cutout: '70%',
				animation: { duration: 850, easing: 'easeOutQuart', animateRotate: true },
				plugins: {
					legend: {
						position: 'bottom',
						labels: {
							color: p.axis,
							usePointStyle: true,
							pointStyle: 'circle',
							boxWidth: 8,
							padding: 12,
							font: { family: 'Geist', size: 11 }
						}
					},
					tooltip: {
						backgroundColor: p.panel,
						titleColor: p.axis,
						bodyColor: p.fg,
						borderColor: p.grid,
						borderWidth: 1,
						padding: 10,
						cornerRadius: 10,
						displayColors: false
					}
				}
			}
		});
	}

	onMount(() => {
		renderDonut();
		renderYearPie();
		return () => {
			chart?.destroy();
			chart = null;
			yearPieChart?.destroy();
			yearPieChart = null;
		};
	});

	$effect(() => {
		[data.outcome.wins, data.outcome.losses, data.outcome.breakeven].join(',');
		void $theme;
		if (donut) renderDonut();
	});

	$effect(() => {
		[yearOutcome.wins, yearOutcome.losses, yearOutcome.breakeven].join(',');
		void $theme;
		tab;
		if (yearPie) renderYearPie();
	});

	function renderYearPie(): void {
		if (!yearPie) return;
		const p = palette();
		Chart.defaults.color = p.axis;
		Chart.defaults.borderColor = p.grid;
		Chart.defaults.font.family = 'Geist, ui-sans-serif, sans-serif';
		yearPieChart?.destroy();
		yearPieChart = new Chart(yearPie, {
			type: 'pie',
			data: {
				labels: ['Winning days', 'Losing days', 'Breakeven'],
				datasets: [
					{
						data: [yearOutcome.wins, yearOutcome.losses, yearOutcome.breakeven],
						backgroundColor: [p.win, p.loss, p.flat],
						borderColor: p.panel,
						borderWidth: 2,
						hoverOffset: 6
					}
				]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				animation: { duration: 850, easing: 'easeOutQuart', animateRotate: true },
				plugins: {
					legend: {
						position: 'bottom',
						labels: {
							color: p.axis,
							usePointStyle: true,
							pointStyle: 'circle',
							boxWidth: 8,
							padding: 12,
							font: { family: 'Geist', size: 11 }
						}
					},
					tooltip: {
						backgroundColor: p.panel,
						titleColor: p.axis,
						bodyColor: p.fg,
						borderColor: p.grid,
						borderWidth: 1,
						padding: 10,
						cornerRadius: 10,
						displayColors: false
					}
				}
			}
		});
	}

	onDestroy(() => {
		chart?.destroy();
		chart = null;
		yearPieChart?.destroy();
		yearPieChart = null;
	});

	const navBtn =
		'grid h-7 w-7 place-items-center rounded-lg border border-line text-mut transition-all duration-200 hover:border-edge hover:text-fg active:scale-95';
</script>

<section class="card p-5" aria-label="Monthly trading calendar">
	<div class="mb-4 flex flex-wrap items-center gap-2">
		<div class="flex items-center gap-1.5">
			{#if tab === 'year'}
				<button type="button" onclick={onPrevYear} aria-label="Previous year" class={navBtn}>‹</button>
				<h2 class="display min-w-40 text-center text-lg text-fg">
					{data.year}
				</h2>
				<button type="button" onclick={onNextYear} aria-label="Next year" class={navBtn}>›</button>
			{:else}
				<button type="button" onclick={onPrev} aria-label="Previous month" class={navBtn}>‹</button>
				<h2 class="display min-w-40 text-center text-lg text-fg">
					{MONTHS[data.month - 1]} {data.year}
				</h2>
				<button type="button" onclick={onNext} aria-label="Next month" class={navBtn}>›</button>
			{/if}
		</div>

		<div class="ml-auto flex flex-wrap items-center gap-2">
			<SegControl
				mode="tabs"
				label="Calendar view"
				value={tab}
				onChange={(v) => (tab = v as 'month' | 'year')}
				size="sm"
				options={[
					{ value: 'month', label: 'Month' },
					{ value: 'year', label: 'Year' }
				]}
			/>
			{#if tab === 'month'}
				<SegControl
					label="Value unit"
					value={unit}
					onChange={(v) => (unit = v as 'usd' | 'pct')}
					size="sm"
					options={[
						{ value: 'usd', label: '$' },
						{ value: 'pct', label: '%' }
					]}
				/>
			{/if}
		</div>
	</div>

	{#key tab}
		<div use:fluidHeight>
		<div in:fly={TAB}>
	{#if tab === 'year'}
		<CalendarHeatmap days={yearDays} year={data.year} />
		<div class="mt-5 grid grid-cols-1 gap-5 md:grid-cols-[240px_minmax(0,1fr)] md:items-center">
			<figure class="mx-auto w-full max-w-60" aria-label="Yearly outcome by day">
				<div class="h-44"><canvas bind:this={yearPie}></canvas></div>
				<figcaption class="num mt-1 text-center text-[11px] text-dim">
					{yearOutcome.wins}W · {yearOutcome.losses}L · {yearOutcome.breakeven}BE over {yearOutcome.days} days
				</figcaption>
			</figure>
			<div class="grid min-w-0 grid-cols-2 gap-2 sm:grid-cols-3" aria-label="Year summary">
				<div class="rise min-w-0 rounded-xl border border-line bg-raised/50 p-3" style="animation-delay: 60ms">
					<p class="text-[11px] text-dim">Trading days</p>
					<p class="num mt-0.5 text-lg font-bold text-fg" use:countup={{ value: yearOutcome.days, format: (v) => `${Math.round(v)}` }}>{yearOutcome.days}</p>
				</div>
				<div class="rise min-w-0 rounded-xl border border-line bg-raised/50 p-3" style="animation-delay: 110ms">
					<p class="text-[11px] text-dim">Day win rate</p>
					<p class="num mt-0.5 text-lg font-bold text-fg" use:countup={{ value: yearOutcome.winRate, format: (v) => `${v.toFixed(1)}%` }}>{yearOutcome.winRate.toFixed(1)}%</p>
				</div>
				<div class="rise min-w-0 rounded-xl border border-line bg-raised/50 p-3" style="animation-delay: 160ms">
					<p class="text-[11px] text-dim">Year net</p>
					<p class="num mt-0.5 text-lg font-bold {valueClass(yearOutcome.net, yearOutcome.days)}" use:countup={{ value: yearOutcome.net, format: (v) => fmtMoney(v) }}>{fmtMoney(yearOutcome.net)}</p>
				</div>
				<div class="rise min-w-0 rounded-xl border border-line bg-raised/50 p-3" style="animation-delay: 210ms">
					<p class="text-[11px] text-dim">Breakeven days</p>
					<p class="num mt-0.5 text-lg font-bold text-flat" use:countup={{ value: yearOutcome.breakeven, format: (v) => `${Math.round(v)}` }}>{yearOutcome.breakeven}</p>
				</div>
				<div class="rise min-w-0 rounded-xl border border-win/25 bg-win/8 p-3" style="animation-delay: 260ms">
					<p class="text-[11px] text-dim">Winning days</p>
					<p class="num mt-0.5 text-lg font-bold text-win" use:countup={{ value: yearOutcome.wins, format: (v) => `${Math.round(v)}` }}>{yearOutcome.wins}</p>
				</div>
				<div class="rise min-w-0 rounded-xl border border-loss/25 bg-loss/8 p-3" style="animation-delay: 310ms">
					<p class="text-[11px] text-dim">Losing days</p>
					<p class="num mt-0.5 text-lg font-bold text-loss" use:countup={{ value: yearOutcome.losses, format: (v) => `${Math.round(v)}` }}>{yearOutcome.losses}</p>
				</div>
			</div>
		</div>
	{:else}
		<div class="grid grid-cols-1 gap-5 xl:grid-cols-4">
			<div class="min-w-0 xl:col-span-3">
				<div class="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-5">
					{#each data.weeks as w, wi}
						<div
							class="rise rounded-xl border border-line bg-raised/50 px-2.5 py-2 transition-colors duration-200 hover:border-edge"
							style="animation-delay: {wi * 45}ms"
						>
							<p class="font-mono text-[10px] tracking-[0.14em] text-dim uppercase">{w.label}</p>
							<p class="num mt-0.5 text-sm font-semibold {valueClass(w.net_pnl, w.trade_count)}">
								<span use:countup={{ value: w.net_pnl, format: (v) => (unit === 'usd' ? fmtMoney(v) : dayValue(v)) }}>
									{unit === 'usd' ? fmtMoney(w.net_pnl) : dayValue(w.net_pnl)}
								</span>
							</p>
							<p class="num text-[10px] text-dim">{w.trade_count} trades</p>
						</div>
					{/each}
				</div>

				<div class="grid grid-cols-7 gap-1.5 sm:gap-2" role="grid" aria-label="{MONTHS[data.month - 1]} day grid">
					{#each ['M', 'T', 'W', 'T', 'F', 'S', 'S'] as d, i (i)}
						<p class="pb-1 text-center font-mono text-[10px] tracking-widest text-dim">{d}</p>
					{/each}
					{#key `${data.year}-${data.month}`}
						{#each cells as c, ci}
							{#if c.blank}
								<div></div>
							{:else}
								{@const info = data.days[c.key] ?? { net_pnl: 0, trade_count: 0, outcome: 'inactive' }}
								<button
									type="button"
									onclick={() => openDay(c.key)}
									aria-label="{c.key}: {fmtMoney(info.net_pnl)}, {info.trade_count} trades — open day"
									title="{c.key}: {fmtMoney(info.net_pnl)} · {info.trade_count} trades"
									class="anim-tile {cellClass(info.outcome, c.key === todayKey)} cursor-pointer focus-visible:outline-2 focus-visible:outline-accent"
									style="animation-delay: {Math.min(ci * 8, 320)}ms"
								>
									<p class="num text-[10px] leading-none {c.key === todayKey ? 'font-bold text-accent' : 'text-mut'}">
										{c.day}
									</p>
									{#if info.trade_count > 0}
										<p class="mt-1 truncate font-mono text-[9.5px] leading-tight font-semibold tabular-nums sm:text-xs {valueClass(info.net_pnl, info.trade_count)}">
											<span class="sm:hidden">{compactValue(info.net_pnl)}</span>
											<span class="hidden sm:inline">{dayValue(info.net_pnl)}</span>
										</p>
										<p class="num text-[9px] leading-tight text-dim">{info.trade_count}T</p>
									{/if}
								</button>
							{/if}
						{/each}
					{/key}
				</div>
			</div>

			<aside class="flex min-w-0 flex-col gap-3" aria-label="Month summary">
				<div class="h-44"><canvas bind:this={donut}></canvas></div>
				<div class="grid grid-cols-2 gap-2">
					<div class="rise rounded-xl border border-line bg-raised/50 p-3" style="animation-delay: 60ms">
						<p class="text-[11px] text-dim">Trading days</p>
						<p class="num text-lg font-bold text-fg" use:countup={{ value: data.summary.trading_days, format: (v) => `${Math.round(v)}` }}>{data.summary.trading_days}</p>
					</div>
					<div class="rise rounded-xl border border-line bg-raised/50 p-3" style="animation-delay: 120ms">
						<p class="text-[11px] text-dim">Day win rate</p>
						<p class="num text-lg font-bold text-fg" use:countup={{ value: data.summary.day_win_rate, format: (v) => `${v.toFixed(1)}%` }}>{data.summary.day_win_rate.toFixed(1)}%</p>
					</div>
					<div class="rise rounded-xl border border-win/25 bg-win/8 p-3" style="animation-delay: 180ms">
						<p class="text-[11px] text-dim">Winning days</p>
						<p class="num text-lg font-bold text-win" use:countup={{ value: data.summary.winning_days, format: (v) => `${Math.round(v)}` }}>{data.summary.winning_days}</p>
					</div>
					<div class="rise rounded-xl border border-loss/25 bg-loss/8 p-3" style="animation-delay: 240ms">
						<p class="text-[11px] text-dim">Losing days</p>
						<p class="num text-lg font-bold text-loss" use:countup={{ value: data.summary.losing_days, format: (v) => `${Math.round(v)}` }}>{data.summary.losing_days}</p>
					</div>
				</div>
			</aside>
		</div>
	{/if}
		</div>
		</div>
	{/key}
</section>
