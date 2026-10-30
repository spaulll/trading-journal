<script lang="ts">
	import { onMount } from 'svelte';
	import { Clock3, CalendarClock } from 'lucide-svelte';
	import {
		api,
		errMsg,
		type BrokerClockDto,
		type BrokerClockListDto,
		type TradingDayDto
	} from '$lib/api';
	import { toasts } from '$lib/stores/toast';
	import { refreshBrokerOffset } from '$lib/stores/broker';
	import { fmtDateTime } from '$lib/utils/format';

	let data = $state<BrokerClockListDto | null>(null);
	let day = $state<TradingDayDto | null>(null);
	let firm = $state('');
	let error = $state<string | null>(null);
	let loading = $state(true);
	let saving = $state(false);
	let savingDay = $state(false);
	let advanced = $state(false);

	let baseMinutes = $state(120);
	let dstRule = $state('us');
	let overrideOpen = $state(false);
	let overrideMinutes = $state(180);
	let dayHour = $state(17);
	let dayZone = $state('America/New_York');

	const clock = $derived<BrokerClockDto | null>(
		data?.clocks.find((c) => c.firm === firm) ?? data?.clocks[0] ?? null
	);
	const namedFirms = $derived((data?.clocks ?? []).filter((c) => c.firm !== ''));
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

	function stamp(iso: string): string {
		return `${iso.slice(0, 16).replace('T', ' ')} UTC · ${fmtDateTime(iso)}`;
	}

	function syncForm(next: BrokerClockDto | null): void {
		if (!next) return;
		baseMinutes = next.base_offset_minutes ?? 120;
		dstRule = next.dst ?? 'us';
		overrideMinutes = next.offset_minutes ?? baseMinutes;
	}

	async function reload(): Promise<void> {
		const [clocks, tradingDay] = await Promise.all([
			api.getBrokerClock(),
			api.getTradingDay()
		]);
		data = clocks;
		day = tradingDay;
		if (!firm) firm = clocks.clocks[0]?.firm ?? '';
		syncForm(clocks.clocks.find((c) => c.firm === firm) ?? clocks.clocks[0] ?? null);
		dayHour = tradingDay.boundary_hour;
		dayZone = tradingDay.timezone;
	}

	onMount(() => {
		void (async () => {
			try {
				await reload();
			} catch (e) {
				error = errMsg(e);
			} finally {
				loading = false;
			}
		})();
	});

	function pickFirm(next: string): void {
		firm = next;
		syncForm(data?.clocks.find((c) => c.firm === next) ?? null);
		overrideOpen = false;
	}

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

	function useGftReset(): void {
		void saveDay(17, 'America/New_York');
	}

	const field = 'field font-mono text-[13px]';
	const label = 'flex flex-col gap-1 text-[11px] font-medium tracking-[0.14em] uppercase text-dim';
</script>

<section aria-label="Broker clock" class="card rise flex flex-col p-4 xl:col-span-2">
	<div class="flex flex-wrap items-center gap-x-2 gap-y-1">
		<Clock3 size={16} strokeWidth={2} aria-hidden="true" class="text-accent" />
		<h2 class="text-[15px] font-semibold text-fg">Broker clock</h2>
		<span class="num text-[11px] text-dim">Firm server time · input + day boundary</span>
	</div>

	<p class="mt-1.5 max-w-2xl text-[12px] leading-snug text-mut">
		Your broker's clock is not a fixed number — it moves with daylight saving. Set the winter
		offset once and the calendar it follows; the app works out the rest, including for trades
		you backfill from months ago.
	</p>

	{#if loading}
		<p class="num mt-4 text-[12px] text-dim">Loading…</p>
	{:else if error && !clock}
		<p class="mt-4 text-[13px] font-medium text-loss" role="alert">{error}</p>
	{:else}
		<div class="mt-4 grid gap-3 sm:grid-cols-2">
			{#if namedFirms.length > 1}
				<label class={label}>
					Firm
					<select class={field} value={firm} onchange={(e) => pickFirm(e.currentTarget.value)}>
						{#each namedFirms as item (item.firm)}
							<option value={item.firm}>{item.firm}</option>
						{/each}
					</select>
				</label>
			{:else}
				<div class={label}>
					Firm
					<span class="num text-[13px] normal-case tracking-normal text-fg">
						{firm || clock?.firm || 'Default'}
					</span>
				</div>
			{/if}

			<label class={label}>
				Winter offset (standard time)
				<select class={field} bind:value={baseMinutes}>
					{#each offsets as minutes (minutes)}
						<option value={minutes}>{offLabel(minutes)}</option>
					{/each}
				</select>
			</label>

			<label class={label}>
				Summer time
				<select class={field} bind:value={dstRule}>
					{#each data?.dst_rules ?? [] as rule (rule.value)}
						<option value={rule.value}>{rule.value.toUpperCase()}</option>
					{/each}
				</select>
			</label>

			<div class="flex items-end">
				<button type="button" class="btn h-9 px-4 text-[13px]" onclick={() => void saveClock()} disabled={saving}>
					{saving ? 'Saving…' : 'Save clock'}
				</button>
			</div>
		</div>

		<p class="num mt-2 text-[11px] leading-snug text-dim">{ruleHint}</p>

		<div class="mt-3 rounded-lg border border-line bg-raised/50 px-3 py-2.5">
			<div class="flex flex-wrap items-center gap-x-3 gap-y-1">
				<span class="eyebrow">Right now</span>
				<span class="num text-[15px] font-semibold text-fg">{clock?.label ?? 'not set'}</span>
				{#if clock?.manual}
					<span class="rounded-full border border-accent/40 bg-accent/10 px-2 py-0.5 text-[10px] font-semibold tracking-[0.12em] uppercase text-accent">
						manual correction
					</span>
				{:else if clock?.configured}
					<span class="text-[10px] tracking-[0.12em] uppercase text-dim">automatic</span>
				{/if}
			</div>
			{#if clock?.next_change}
				<p class="num mt-1 text-[11px] text-mut">
					Next change {stamp(clock.next_change.at)} → {clock.next_change.label}
				</p>
			{:else if clock?.dst === 'none'}
				<p class="num mt-1 text-[11px] text-mut">Fixed offset — never changes.</p>
			{/if}
			{#if clock && !clock.configured}
				<p class="num mt-1 text-[11px] text-mut">
					Using the old single-offset setting. Save this rule to replace it.
				</p>
			{/if}
		</div>

		<div class="mt-3 flex flex-wrap items-center gap-2">
			{#if !overrideOpen}
				<button
					type="button"
					class="btn btn-ghost h-8 px-3 text-[12px]"
					onclick={() => {
						overrideMinutes = clock?.offset_minutes ?? baseMinutes;
						overrideOpen = true;
					}}
				>
					MT5 shows something else…
				</button>
			{:else}
				<div class="flex flex-wrap items-end gap-2">
					<label class={label}>
						Actual offset now
						<select class={field} bind:value={overrideMinutes}>
							{#each offsets as minutes (minutes)}
								<option value={minutes}>{offLabel(minutes)}</option>
							{/each}
						</select>
					</label>
					<button type="button" class="btn h-9 px-3 text-[12px]" onclick={() => void saveOverride()} disabled={saving}>
						Record from today
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

		<div class="mt-4 border-t border-line pt-3">
			<div class="flex flex-wrap items-center gap-x-2 gap-y-1">
				<CalendarClock size={15} strokeWidth={2} aria-hidden="true" class="text-accent" />
				<h3 class="text-[13px] font-semibold text-fg">Trading day</h3>
				<span class="num text-[11px] text-dim">{day?.label ?? '—'}</span>
			</div>
			<p class="mt-1 text-[12px] leading-snug text-mut">
				A trade belongs to the day it <span class="text-fg">closes</span>. GFT resets at 5 PM New
				York, which is midnight on a +2/+3 broker.
			</p>
			<div class="mt-2 flex flex-wrap items-center gap-2">
				<button type="button" class="btn btn-ghost h-8 px-3 text-[12px]" onclick={useGftReset} disabled={savingDay}>
					Use GFT reset (5 PM New York)
				</button>
				<button
					type="button"
					class="btn btn-ghost h-8 px-3 text-[12px]"
					onclick={() => (advanced = !advanced)}
					aria-expanded={advanced}
				>
					{advanced ? 'Hide' : 'Advanced'}
				</button>
			</div>
			{#if advanced}
				<div class="mt-2 grid gap-2 sm:grid-cols-3">
					<label class={label}>
						Zone
						<input class={field} bind:value={dayZone} spellcheck="false" />
					</label>
					<label class={label}>
						Hour (0–23)
						<input class={field} type="number" min="0" max="23" bind:value={dayHour} />
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
			{#if day}
				<p class="num mt-2 text-[11px] text-dim">
					Today is {day.today} by this boundary.
				</p>
			{/if}
		</div>

		{#if error}
			<p class="mt-3 text-[13px] font-medium text-loss" role="alert">{error}</p>
		{/if}
	{/if}
</section>
