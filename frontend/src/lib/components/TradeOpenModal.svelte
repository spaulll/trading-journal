<script lang="ts">
	import { Plus, X } from 'lucide-svelte';
	import { fade, scale } from 'svelte/transition';
	import { dismissLifecycle, lifecycleBusy, submitBackfill, submitOpen } from '$lib/stores/trades';
	import { fmtMoney } from '$lib/utils/format';
	import { FADE, MODAL } from '$lib/utils/transitions';

	/** Rough per-unit contract sizes for the risk preview (estimate only). */
	const CONTRACT: { match: RegExp; size: number; unit: string }[] = [
		{ match: /^(xau|gold|paxg)/i, size: 100, unit: 'oz' },
		{ match: /^(xag|silver)/i, size: 5000, unit: 'oz' },
		{ match: /^(eur|gbp|aud|nzd|usd|jpy|chf|cad)/i, size: 100000, unit: 'units' },
		{ match: /^(btc|eth|sol)/i, size: 1, unit: 'coin' }
	];

	let symbol = $state('');
	let direction = $state<'buy' | 'sell'>('buy');
	let size = $state('0.1');
	let entry = $state('');
	let sl = $state('');
	let tp = $state('');
	let tags = $state('');
	let formError = $state<string | null>(null);
	let mode = $state<'live' | 'backfill'>('live');
	// Backfill-only fields (UTC).
	let entryAt = $state('');
	let exitAt = $state('');
	let exitPrice = $state('');
	let netPnl = $state('');

	function sessionForHour(h: number): string {
		if (h < 6) return 'Asia';
		if (h < 7) return 'Outside';
		if (h < 13) return 'London';
		if (h < 22) return 'New York';
		return 'Outside';
	}

	function sessionForUTC(d: Date): string {
		return sessionForHour(d.getUTCHours() + d.getUTCMinutes() / 60);
	}

	const liveSession = $derived(sessionForUTC(new Date()));
	// Session preview parsed from the literal entry stamp (server resolves
	// the same naive-UTC value, so this preview always matches).
	const backfillSession = $derived.by(() => {
		const m = entryAt.trim().match(/T(\d{2}):(\d{2})/);
		if (!m) return null;
		return sessionForHour(parseInt(m[1], 10) + parseInt(m[2], 10) / 60);
	});

	const num = (v: string): number | null => {
		const n = parseFloat(v);
		return v.trim() === '' || Number.isNaN(n) ? null : n;
	};

	const contract = $derived(
		CONTRACT.find((c) => c.match.test(symbol.trim())) ?? { size: 1, unit: 'units' }
	);
	const entryN = $derived(num(entry));
	const slN = $derived(num(sl));
	const tpN = $derived(num(tp));
	const sizeN = $derived(num(size));

	const riskDist = $derived(entryN !== null && slN !== null ? Math.abs(entryN - slN) : null);
	const riskEst = $derived(
		riskDist !== null && sizeN !== null && sizeN > 0 ? riskDist * sizeN * contract.size : null
	);
	const rewardEst = $derived(
		entryN !== null && tpN !== null && sizeN !== null && sizeN > 0
			? Math.abs(tpN - entryN) * sizeN * contract.size
			: null
	);
	const rr = $derived(
		entryN !== null && slN !== null && tpN !== null && riskDist !== null && riskDist > 0
			? Math.abs(tpN - entryN) / riskDist
			: null
	);
	const slSideOk = $derived(
		entryN === null || slN === null
			? true
			: direction === 'buy'
				? slN < entryN
				: slN > entryN
	);

	function onBackdrop(e: MouseEvent): void {
		if (e.target === e.currentTarget) dismissLifecycle();
	}

	async function submit(e: SubmitEvent): Promise<void> {
		e.preventDefault();
		formError = null;
		if (mode === 'backfill') {
			await submitBackfillForm();
			return;
		}
		if (!symbol.trim()) {
			formError = 'Symbol is required.';
			return;
		}
		if (sizeN === null || sizeN <= 0) {
			formError = 'Lot size must be positive.';
			return;
		}
		if (entryN === null || slN === null) {
			formError = 'Entry and stop loss must be numbers.';
			return;
		}
		if (!slSideOk) {
			formError = direction === 'buy' ? 'For a buy, stop loss must be below entry.' : 'For a sell, stop loss must be above entry.';
			return;
		}
		await submitOpen({
			symbol: symbol.trim(),
			direction,
			size: sizeN,
			entry_price: entryN,
			initial_sl: slN,
			tp: tpN,
			tags: tags.split(/[\s,]+/).filter(Boolean)
		});
	}

	const exitN = $derived(num(exitPrice));
	const netN = $derived(netPnl.trim() === '' ? null : num(netPnl));

	async function submitBackfillForm(): Promise<void> {
		if (!symbol.trim()) {
			formError = 'Symbol is required.';
			return;
		}
		if (sizeN === null || sizeN <= 0) {
			formError = 'Lot size must be positive.';
			return;
		}
		if (entryN === null) {
			formError = 'Entry price must be a number.';
			return;
		}
		if (exitN === null) {
			formError = 'Exit price must be a number.';
			return;
		}
		if (!entryAt.trim() || !exitAt.trim()) {
			formError = 'Entry and exit date/time are required (UTC).';
			return;
		}
		const entryIso = `${entryAt.trim()}:00`;
		const exitIso = `${exitAt.trim()}:00`;
		if (exitIso <= entryIso) {
			formError = 'Exit must be after entry.';
			return;
		}
		await submitBackfill({
			symbol: symbol.trim(),
			direction,
			size: sizeN,
			entry_price: entryN,
			exit_price: exitN,
			entry_time: entryIso,
			exit_time: exitIso,
			initial_sl: slN,
			tp: tpN,
			net_pnl: netN,
			tags: tags.split(/[\s,]+/).filter(Boolean)
		});
	}

	const field =
		'h-10 w-full rounded-lg border border-slate-200 bg-transparent px-3 font-mono text-sm tabular-nums outline-none placeholder:text-slate-400 focus:border-emerald-500 dark:border-white/10';
	const label = 'flex flex-col gap-1.5 text-xs font-semibold tracking-tight text-slate-500 dark:text-slate-400';
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && dismissLifecycle()} />

<div
	transition:fade={FADE}
	onclick={onBackdrop}
	onkeydown={(e) => e.key === 'Escape' && dismissLifecycle()}
	tabindex={-1}
	class="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-surface-950/70 p-4 backdrop-blur-sm"
	role="dialog"
	aria-modal="true"
	aria-label="Open trade"
>
	<div transition:scale={MODAL} class="w-full max-w-lg rounded-2xl border border-slate-200 bg-white shadow-pop dark:border-white/[0.08] dark:bg-surface-900">
		<div class="flex items-center gap-2 border-b border-slate-200 px-5 py-4 dark:border-white/[0.07]">
			<Plus size={17} strokeWidth={2} aria-hidden="true" class="text-emerald-500" />
			<h2 class="text-sm font-semibold tracking-tight">Open trade</h2>
			<button
				type="button"
				onclick={() => dismissLifecycle()}
				aria-label="Close"
				class="ml-auto grid h-8 w-8 place-items-center rounded-lg text-slate-400 transition-all hover:bg-slate-100 hover:text-slate-700 focus-visible:outline-emerald-500 active:scale-95 dark:hover:bg-white/[0.06] dark:hover:text-slate-200"
			>
				<X size={17} strokeWidth={1.8} aria-hidden="true" />
			</button>
		</div>

		<form class="px-5 py-4" onsubmit={submit}>
			<div class="mb-3 grid grid-cols-2 gap-1 rounded-lg border border-slate-200 p-1 dark:border-white/10" role="group" aria-label="Entry mode">
				<button
					type="button"
					onclick={() => (mode = 'live')}
					aria-pressed={mode === 'live'}
					class="rounded-md py-1.5 text-sm font-semibold transition-all duration-150 focus-visible:outline-emerald-500 {mode === 'live'
						? 'bg-emerald-500 text-white shadow'
						: 'text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white'}"
				>
					Live Trade
				</button>
				<button
					type="button"
					onclick={() => (mode = 'backfill')}
					aria-pressed={mode === 'backfill'}
					class="rounded-md py-1.5 text-sm font-semibold transition-all duration-150 focus-visible:outline-emerald-500 {mode === 'backfill'
						? 'bg-emerald-500 text-white shadow'
						: 'text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white'}"
				>
					Historical / Backfill
				</button>
			</div>
			<div class="grid grid-cols-2 gap-3">
				<label class={label}>
					Symbol
					<input type="text" bind:value={symbol} placeholder="GOLD" autocomplete="off" class="{field} uppercase" />
				</label>
				<span class={label}>
					Direction
					<span class="grid h-10 grid-cols-2 gap-1 rounded-lg border border-slate-200 p-1 dark:border-white/10">
						{#each (['buy', 'sell'] as const) as d}
							<button
								type="button"
								onclick={() => (direction = d)}
								aria-pressed={direction === d}
								class="rounded-md font-mono text-sm font-bold uppercase transition-all duration-150 focus-visible:outline-emerald-500 {direction === d
									? d === 'buy'
										? 'bg-emerald-500 text-white shadow'
										: 'bg-rose-500 text-white shadow'
									: 'text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white'}"
							>
								{d === 'buy' ? 'Buy' : 'Sell'}
							</button>
						{/each}
					</span>
				</span>
				<label class={label}>
					Lot size
					<input type="number" value={size} oninput={(e) => (size = e.currentTarget.value)} min="0" step="any" class={field} />
				</label>
				<label class={label}>
					Entry price
					<input type="number" value={entry} oninput={(e) => (entry = e.currentTarget.value)} step="any" placeholder="4305.00" class={field} />
				</label>
				<label class={label}>
					Initial stop loss
					<input type="number" value={sl} oninput={(e) => (sl = e.currentTarget.value)} step="any" placeholder="4298.00" class={field} />
				</label>
				<label class={label}>
					Take profit <span class="font-normal opacity-70">(optional)</span>
					<input type="number" value={tp} oninput={(e) => (tp = e.currentTarget.value)} step="any" placeholder="4325.00" class={field} />
				</label>
			</div>
			<label class="{label} mt-3">
				Setup tags <span class="font-mono font-normal">#fvg #bos</span>
				<input type="text" bind:value={tags} placeholder="#breakout" autocomplete="off" class="{field} font-sans" />
			</label>

			{#if mode === 'backfill'}
				<fieldset class="mt-3 rounded-xl border border-slate-200 p-3 dark:border-white/10">
					<legend class="px-1 font-mono text-[11px] tracking-wider text-slate-400 uppercase">Historical exit (UTC)</legend>
					<div class="grid grid-cols-2 gap-3">
						<label class={label}>
							Entry date/time
							<input type="datetime-local" value={entryAt} oninput={(e) => (entryAt = e.currentTarget.value)} class={field} />
						</label>
						<label class={label}>
							Exit date/time
							<input type="datetime-local" value={exitAt} oninput={(e) => (exitAt = e.currentTarget.value)} class={field} />
						</label>
						<label class={label}>
							Exit price
							<input type="number" value={exitPrice} oninput={(e) => (exitPrice = e.currentTarget.value)} step="any" class={field} />
						</label>
						<label class={label}>
							Net PnL <span class="font-normal opacity-70">(optional)</span>
							<input type="number" value={netPnl} oninput={(e) => (netPnl = e.currentTarget.value)} step="any" class={field} />
						</label>
					</div>
					<p class="mt-2 font-mono text-[11px] tabular-nums text-slate-500 dark:text-slate-400" aria-live="polite">
						Session: <span class="font-bold">{backfillSession ?? '— pick entry time —'}</span>
					</p>
				</fieldset>
			{/if}

			<div class="mt-4 rounded-xl border border-slate-200 bg-slate-50/70 px-3.5 py-3 dark:border-white/[0.07] dark:bg-white/[0.02]" aria-live="polite">
				<p class="font-mono text-[11px] tracking-wider text-slate-400 uppercase">
					{mode === 'live' ? 'Risk preview' : 'Backfill preview'} <span class="normal-case">(estimate)</span>
				</p>
				{#if mode === 'live'}
					<p class="mt-1 font-mono text-[11px] tabular-nums text-slate-500 dark:text-slate-400">
						Entry now · Session: <span class="font-bold text-slate-700 dark:text-slate-200">{liveSession}</span> (auto)
					</p>
				{/if}
				{#if riskEst !== null && riskDist !== null}
					<p class="mt-1 font-mono text-sm tabular-nums">
						Risk <span class="font-bold text-rose-600 dark:text-rose-400">{fmtMoney(riskEst)}</span>
						<span class="text-slate-500 dark:text-slate-400">· {riskDist} pts</span>
						{#if rewardEst !== null}
							<span class="text-slate-500 dark:text-slate-400"> · Reward {fmtMoney(rewardEst)}</span>
						{/if}
						{#if rr !== null}
							<span class="font-bold text-emerald-600 dark:text-emerald-400"> · {rr.toFixed(2)}R</span>
						{/if}
					</p>
				{:else}
					<p class="mt-1 text-sm text-slate-500 dark:text-slate-400">Type entry, stop and size to preview risk.</p>
				{/if}
				{#if !slSideOk}
					<p class="mt-1 text-[13px] font-medium text-rose-600 dark:text-rose-400">Stop is on the wrong side of entry for a {direction}.</p>
				{/if}
			</div>

			{#if formError}
				<p class="mt-3 text-[13px] font-medium text-rose-600 dark:text-rose-400" role="alert">{formError}</p>
			{/if}

			<div class="mt-4 flex justify-end gap-2">
				<button
					type="button"
					onclick={() => dismissLifecycle()}
					class="h-10 rounded-lg border border-slate-200 px-4 text-sm font-semibold transition-all hover:border-slate-300 focus-visible:outline-emerald-500 active:scale-[0.98] dark:border-white/10"
				>
					Cancel
				</button>
				<button
					type="submit"
					disabled={$lifecycleBusy}
					class="h-10 rounded-lg bg-emerald-500 px-5 text-sm font-semibold text-white shadow-lift transition-all duration-150 hover:bg-emerald-600 focus-visible:outline-emerald-500 active:scale-[0.98] disabled:cursor-wait disabled:opacity-70"
				>
					{$lifecycleBusy ? (mode === 'live' ? 'Opening…' : 'Saving…') : mode === 'live' ? 'Open trade' : 'Backfill trade'}
				</button>
			</div>
		</form>
	</div>
</div>
