<script lang="ts">
	import { get } from 'svelte/store';
	import { onMount } from 'svelte';
	import { CalendarClock, Clock3, SlidersHorizontal, Timer } from 'lucide-svelte';
	import {
		api,
		errMsg,
		type BrokerClockDto,
		type BrokerClockListDto,
		type TradingDayDto
	} from '$lib/api';
	import { selectedAccount } from '$lib/stores/accounts';
	import { refreshBrokerOffset } from '$lib/stores/broker';
	import { toasts } from '$lib/stores/toast';

	const IST_ZONE = 'Asia/Kolkata';
	const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
	const label = 'flex flex-col gap-1 text-[11px] font-medium tracking-[0.14em] uppercase text-dim';

	let data = $state<BrokerClockListDto | null>(null);
	let day = $state<TradingDayDto | null>(null);
	let firm = $state('');
	let error = $state<string | null>(null);
	let loading = $state(true);
	let saving = $state(false);
	let savingDay = $state(false);

	// Live tickers.
	let nowMs = $state(0);
	let adjust = $state(false);
	let overrideOpen = $state(false);
	let dayAdvanced = $state(false);

	// Rule form.
	let baseMinutes = $state(120);
	let dstRule = $state('us');
	let overrideMinutes = $state(180);
	let dayHour = $state(17);
	let dayZone = $state('America/New_York');

	const clock = $derived<BrokerClockDto | null>(
		data?.clocks.find((c) => c.firm === firm) ?? data?.clocks[0] ?? null
	);
	const firms = $derived((data?.clocks ?? []).filter((c) => c.firm !== ''));
	const ruleHint = $derived(
		data?.dst_rules.find((r) => r.value === dstRule)?.label ?? 'No daylight saving'
	);

	/** −12:00 … +14:00 in half-hour steps. */
	const offsets = Array.from({ length: 53 }, (_, i) => -720 + i * 30);

	function offLabel(minutes: number): string {
		const sign = minutes >= 0 ? '+' : '−';
		const total = Math.abs(minutes);
		return `UTC${sign}${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
	}

	function clockParts(ms: number, zone: string): { time: string; date: string } {
		const time = new Intl.DateTimeFormat('en-GB', {
			timeZone: zone,
			hour: '2-digit',
			minute: '2-digit',
			second: '2-digit',
			hour12: true
		}).format(ms);
		const date = new Intl.DateTimeFormat('en-GB', {
			timeZone: zone,
			weekday: 'short',
			day: 'numeric',
			month: 'short'
		}).format(ms);
		return { time, date };
	}

	function brokerParts(ms: number, offsetMinutes: number): { time: string; date: string } {
		const shifted = new Date(ms + offsetMinutes * 60_000);
		return clockParts(shifted.valueOf(), 'UTC');
	}

	/** How far ahead/behind of IST the broker runs, e.g. "2 h 30 min behind". */
	function relativeToIst(offsetMinutes: number): string {
		const delta = offsetMinutes - 330; // broker − IST, in minutes
		if (delta === 0) return 'matches your clock';
		const abs = Math.abs(delta);
		const h = Math.floor(abs / 60);
		const m = abs % 60;
		const piece = h > 0 ? `${h} h${m ? ` ${m} min` : ''}` : `${m} min`;
		return delta > 0 ? `is ${piece} ahead of your clock` : `is ${piece} behind your clock`;
	}

	function utcStamp(iso: string): string {
		const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
		return `${d} ${MONTHS[m - 1]} ${y} · ${iso.slice(11, 16)} UTC`;
	}

	const istTile = $derived(nowMs ? clockParts(nowMs, IST_ZONE) : null);
	const brokerTile = $derived(nowMs && clock ? brokerParts(nowMs, clock.offset_minutes ?? 0) : null);
	const km = $derived.by(() => {
		if (!brokerTile || !clock) return null;
		return { delta: relativeToIst(clock.offset_minutes ?? 0), expect: brokerTile.time };
	});

	function syncForm(next: BrokerClockDto | null): void {
		if (!next) return;
		baseMinutes = next.base_offset_minutes ?? 120;
		dstRule = next.dst ?? 'us';
		overrideMinutes = next.offset_minutes ?? baseMinutes;
	}

	function pickFirm(next: string): void {
		firm = next;
		syncForm(data?.clocks.find((c) => c.firm === next) ?? null);
		overrideOpen = false;
	}

	async function reload(): Promise<void> {
		const [clocks, tradingDay] = await Promise.all([api.getBrokerClock(), api.getTradingDay()]);
		data = clocks;
		day = tradingDay;
		const preferred = get(selectedAccount)?.firm?.trim();
		if (!firm) {
			firm =
				preferred && clocks.clocks.some((c) => c.firm === preferred)
					? preferred
					: (clocks.clocks[0]?.firm ?? '');
		}
		syncForm(clocks.clocks.find((c) => c.firm === firm) ?? clocks.clocks[0] ?? null);
		dayHour = tradingDay.boundary_hour;
		dayZone = tradingDay.timezone;
	}

	onMount(() => {
		nowMs = Date.now();
		const timer = setInterval(() => (nowMs = Date.now()), 1000);
		void (async () => {
			try {
				await reload();
			} catch (e) {
				error = errMsg(e);
			} finally {
				loading = false;
			}
		})();
		return () => clearInterval(timer);
	});

	async function saveClock(): Promise<void> {
		if (saving) return;
		saving = true;
		error = null;
		try {
			const saved = await api.putBrokerClock({
				firm: firm || null,
				base_offset_minutes: baseMinutes,
				dst: dstRule
			});
			data = await api.getBrokerClock();
			syncForm(saved);
			await refreshBrokerOffset();
			toasts.push('success', `Broker clock saved — ${saved.label ?? 'set'} right now.`);
		} catch (e) {
			error = errMsg(e);
		} finally {
			saving = false;
		}
	}

	async function saveOverride(): Promise<void> {
		if (saving) return;
		saving = true;
		error = null;
		try {
			const saved = await api.overrideBrokerClock({
				firm: firm || null,
				offset_minutes: overrideMinutes
			});
			data = await api.getBrokerClock();
			syncForm(saved);
			overrideOpen = false;
			await refreshBrokerOffset();
			toasts.push('success', `Correction recorded from today — ${saved.label ?? ''}.`);
		} catch (e) {
			error = errMsg(e);
		} finally {
			saving = false;
		}
	}

	async function clearOverride(): Promise<void> {
		if (saving) return;
		saving = true;
		error = null;
		try {
			const saved = await api.clearBrokerClockOverride(firm || null);
			data = await api.getBrokerClock();
			syncForm(saved);
			await refreshBrokerOffset();
			toasts.push('info', 'Manual corrections cleared — the automatic rule is back.');
		} catch (e) {
			error = errMsg(e);
		} finally {
			saving = false;
		}
	}

	async function saveDay(hour: number, zone: string): Promise<void> {
		if (savingDay) return;
		savingDay = true;
		error = null;
		try {
			day = await api.putTradingDay({ boundary_hour: hour, timezone: zone });
			dayHour = day.boundary_hour;
			dayZone = day.timezone;
			toasts.push('success', `Trading day now rolls at ${day.label}.`);
		} catch (e) {
			error = errMsg(e);
		} finally {
			savingDay = false;
		}
	}
</script>

<section aria-label="Broker clock" class="card rise flex flex-col p-4 xl:col-span-2">
	<div class="flex flex-wrap items-center justify-between gap-3">
		<div class="flex min-w-0 items-center gap-2">
			<Clock3 size={16} strokeWidth={2} aria-hidden="true" class="shrink-0 text-accent" />
			<h2 class="truncate text-[15px] font-semibold text-fg">Broker clock</h2>
			<span class="num hidden text-[11px] text-dim sm:inline">IST vs broker · live</span>
		</div>
		<div class="flex flex-wrap items-center gap-2">
			{#if clock}
				<span class="num inline-flex items-center gap-1.5 rounded-pill border border-line bg-raised/60 px-2.5 py-1 text-[11px] text-fg">
					<span class="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" aria-hidden="true"></span>
					{clock.label}
				</span>
				{#if clock.manual}
					<span class="rounded-pill border border-accent/40 bg-accent/10 px-2.5 py-1 text-[10px] font-semibold tracking-[0.1em] uppercase text-accent">
						manual
					</span>
				{/if}
			{/if}
			{#if firms.length > 1}
				<div class="flex items-center gap-1" role="group" aria-label="Firm">
					{#each firms as item (item.firm)}
						<button
							type="button"
							class="chip h-8 px-3 text-[12px]"
							data-active={item.firm === firm}
							onclick={() => pickFirm(item.firm)}
						>
							{item.firm}
						</button>
					{/each}
				</div>
			{/if}
		</div>
	</div>

	{#if loading}
		<div class="mt-6 flex items-center gap-2 text-[13px] text-dim">
			<Timer size={15} strokeWidth={2} aria-hidden="true" class="animate-pulse" />
			Checking the broker clock…
		</div>
	{:else if error && !clock}
		<p class="mt-6 text-[13px] font-medium text-loss" role="alert">{error}</p>
	{:else}
		<!-- Two live clocks -->
		<div class="mt-4 grid gap-3 sm:grid-cols-2">
			<div class="rounded-card border border-line bg-panel px-4 py-3">
				<div class="eyebrow">You · IST</div>
				<div class="mt-1.5 font-mono text-[34px] font-semibold leading-none tracking-tight text-fg tabular-nums">
					{istTile?.time ?? '—:—:—'}
				</div>
				<div class="num mt-2.5 text-[11px] uppercase tracking-[0.18em] text-dim">{istTile?.date ?? '—'}</div>
			</div>
			<div class="relative rounded-card border border-accent/30 bg-panel px-4 py-3">
				<div class="flex items-center justify-between gap-2">
					<div class="eyebrow">Broker · {clock?.firm || 'default'}</div>
					{#if clock}
						<span class="num text-[11px] text-dim">{clock.label}</span>
					{/if}
				</div>
				<div class="mt-1.5 font-mono text-[34px] font-semibold leading-none tracking-tight text-fg tabular-nums">
					{brokerTile?.time ?? '—:—:—'}
				</div>
				<div class="num mt-2.5 text-[11px] uppercase tracking-[0.18em] text-dim">
					{brokerTile?.date ?? '—'}
				</div>
			</div>
		</div>

		<!-- The check the trader actually needs to make -->
		<div class="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-control border border-line bg-raised/40 px-3 py-2.5">
			<span class="num text-[12px] leading-snug text-fg">
				Your broker {km?.delta ?? '—'}.
				<span class="text-dim"> MT5 should read</span> {brokerTile?.time ?? '—'}
			</span>
			{#if !overrideOpen}
				<button
					type="button"
					class="btn btn-ghost h-8 px-3 text-[12px]"
					onclick={() => {
						overrideMinutes = clock?.offset_minutes ?? baseMinutes;
						overrideOpen = true;
					}}
				>
					MT5 shows a different time…
				</button>
			{:else}
				<div class="flex flex-wrap items-end gap-2">
					<label class={label}>
						Actual offset now
						<select class="field h-9 px-2 text-[12px]" bind:value={overrideMinutes}>
							{#each offsets as minutes (minutes)}
								<option value={minutes}>{offLabel(minutes)}</option>
							{/each}
						</select>
					</label>
					<button type="button" class="btn h-9 px-3 text-[12px]" onclick={() => void saveOverride()} disabled={saving}>
						Record
					</button>
					<button type="button" class="btn btn-ghost h-9 px-3 text-[12px]" onclick={() => (overrideOpen = false)}>
						Cancel
					</button>
				</div>
			{/if}
			{#if clock?.overrides.length}
				<button type="button" class="btn btn-ghost h-8 px-3 text-[12px]" onclick={() => void clearOverride()} disabled={saving}>
					Clear correction
				</button>
			{/if}
		</div>
		<p class="num mt-1.5 text-[11px] leading-snug text-dim">
			Open your MT5 terminal — if its clock differs from the one above, the rule is off. Record a
			correction and it stays until you clear it.
		</p>

		<!-- Status strip -->
		<div class="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line pt-3">
			{#if clock?.next_change}
				<span class="num text-[11px] text-mut">
					Next change → {clock.next_change.label} on {utcStamp(clock.next_change.at)}
				</span>
			{:else if clock?.dst === 'none'}
				<span class="num text-[11px] text-mut">Fixed offset — never changes.</span>
			{/if}
			{#if clock && !clock.configured}
				<span class="num text-[11px] text-accent">
					Using the old single-offset setting — save a rule to replace it.
				</span>
			{/if}
		</div>

		<!-- Rule -->
		<div class="mt-3 flex flex-wrap items-center gap-2">
			<button
				type="button"
				class="btn btn-ghost h-8 px-3 text-[12px]"
				onclick={() => (adjust = !adjust)}
				aria-expanded={adjust}
			>
				<SlidersHorizontal size={14} strokeWidth={2} aria-hidden="true" />
				{adjust ? 'Hide clock rule' : 'Adjust clock'}
			</button>
		</div>
		{#if adjust}
			<div class="mt-3 grid gap-x-3 gap-y-3 rounded-control border border-line bg-panel/60 p-3 sm:grid-cols-3">
				{#if firms.length > 1}
					<label class={label}>
						Firm
						<select class="field" value={firm} onchange={(e) => pickFirm(e.currentTarget.value)}>
							{#each firms as item (item.firm)}
								<option value={item.firm}>{item.firm}</option>
							{/each}
						</select>
					</label>
				{/if}
				<label class={label}>
					Winter offset (standard time)
					<select class="field" bind:value={baseMinutes}>
						{#each offsets as minutes (minutes)}
							<option value={minutes}>{offLabel(minutes)}</option>
						{/each}
					</select>
				</label>
				<label class={label}>
					Summer time
					<select class="field" bind:value={dstRule}>
						{#each data?.dst_rules ?? [] as rule (rule.value)}
							<option value={rule.value}>{rule.value.toUpperCase()}</option>
						{/each}
					</select>
				</label>
				<div class="flex items-end">
					<button type="button" class="btn h-9 px-4 text-[13px]" onclick={() => void saveClock()} disabled={saving}>
						{saving ? 'Saving…' : 'Save'}
					</button>
				</div>
			</div>
			<p class="num mt-2 text-[11px] leading-snug text-dim">{ruleHint}</p>
		{/if}

		<!-- Trading day -->
		<div class="mt-4 border-t border-line pt-3">
			<div class="flex flex-wrap items-center gap-x-2 gap-y-1">
				<CalendarClock size={15} strokeWidth={2} aria-hidden="true" class="text-accent" />
				<h3 class="text-[13px] font-semibold text-fg">Trading day</h3>
				<span class="num text-[11px] text-dim">{day?.label ?? '—'}</span>
				{#if day}
					<span class="num text-[11px] text-mut">· today is {day.today}</span>
				{/if}
			</div>
			<p class="mt-1 text-[12px] leading-snug text-mut">
				A trade belongs to the day it <span class="text-fg">closes</span>. This sets when a
				new trading day starts — one menu for every firm.
			</p>
			<div class="mt-2 flex flex-wrap items-center gap-2">
				<button
					type="button"
					class="btn btn-ghost h-8 px-3 text-[12px]"
					onclick={() => void saveDay(17, 'America/New_York')}
					disabled={savingDay}
				>
					5&#8202;PM New York
				</button>
				<button
					type="button"
					class="btn btn-ghost h-8 px-3 text-[12px]"
					onclick={() => void saveDay(0, 'Asia/Kolkata')}
					disabled={savingDay}
				>
					Local midnight
				</button>
				<button
					type="button"
					class="btn btn-ghost h-8 px-3 text-[12px]"
					onclick={() => (dayAdvanced = !dayAdvanced)}
					aria-expanded={dayAdvanced}
				>
					{dayAdvanced ? 'Hide' : 'Advanced'}
				</button>
			</div>
			{#if dayAdvanced}
				<div class="mt-2 grid gap-2 sm:grid-cols-3">
					<label class={label}>
						Zone
						<input class="field" bind:value={dayZone} spellcheck="false" />
					</label>
					<label class={label}>
						Hour (0–23)
						<input class="field" type="number" min="0" max="23" bind:value={dayHour} />
					</label>
					<div class="flex items-end">
						<button
							type="button"
							class="btn h-9 px-4 text-[13px]"
							onclick={() => void saveDay(dayHour, dayZone)}
							disabled={savingDay}
						>
							{savingDay ? 'Saving…' : 'Save day'}
						</button>
					</div>
				</div>
			{/if}
		</div>

		{#if error}
			<p class="mt-3 text-[13px] font-medium text-loss" role="alert">{error}</p>
		{/if}
	{/if}
</section>
