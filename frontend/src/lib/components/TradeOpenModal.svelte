<script lang="ts">
	import { Plus, X } from 'lucide-svelte';
	import { fade, scale } from 'svelte/transition';
	import { dismissLifecycle, lifecycleBusy, submitBackfill, submitOpen } from '$lib/stores/trades';
	import { accounts, loadAccounts } from '$lib/stores/accounts';
	import { fmtCurrency, fmtMoney, mt5WallToUTC, previewIST, previewMT5 } from '$lib/utils/format';
	import { brokerOffset } from '$lib/stores/broker';
	import { loadSymbols, previewSymbol, specFor, symbolMap, symbols } from '$lib/stores/symbols';
	import type { SymbolPreviewDto } from '$lib/api';
	import { FADE, MODAL, PANEL_FADE } from '$lib/utils/transitions';
	import { dialogEscape } from '$lib/utils/dialogs';
	import SegControl from '$lib/components/SegControl.svelte';
	import TagInput from '$lib/components/TagInput.svelte';
	import { fluidHeight } from '$lib/utils/motion';
	import { onMount } from 'svelte';

	onMount(() => {
		void loadAccounts();
		void loadSymbols();
		try {
			accountSel = localStorage.getItem('selected-account-id') ?? '';
		} catch {
			// ignore
		}
	});

	let symbol = $state('');
	let direction = $state<'buy' | 'sell'>('buy');
	let size = $state('0.1');
	let entry = $state('');
	let sl = $state('');
	let tp = $state('');
	let tags = $state('');
	let accountSel = $state('');
	let formError = $state<string | null>(null);
	let mode = $state<'live' | 'backfill'>('live');
	// Live explicit entry (UTC); empty = now.
	let liveEntryAt = $state('');
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

	/** UTC instant for a wall input in the current zone (null when invalid). */
	function inputToUTCDate(raw: string): Date | null {
		const t = raw.trim();
		if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(t)) return null;
		const iso = $brokerOffset ? mt5WallToUTC(t, $brokerOffset.minutes) : `${t}:00`;
		if (!iso) return null;
		const d = new Date(`${iso}Z`);
		return Number.isNaN(d.getTime()) ? null : d;
	}

	const timePreview = (raw: string): string => {
		if ($brokerOffset) return previewMT5(raw, $brokerOffset.minutes);
		return previewIST(raw);
	};

	/** Wall input → UTC `YYYY-MM-DDTHH:MM:SS` for the API; sets formError on failure. */
	function toSubmitTime(raw: string, label: string): string | null {
		const d = inputToUTCDate(raw);
		if (!d) {
			formError = `${label} must be a valid date/time.`;
			return null;
		}
		return d.toISOString().slice(0, 19);
	}

	const zoneTag = (fallback: string): string =>
		$brokerOffset ? `MT5 · ${$brokerOffset.label}` : fallback;

	function sessionForUTC(d: Date): string {
		return sessionForHour(d.getUTCHours() + d.getUTCMinutes() / 60);
	}

	const liveSession = $derived.by(() => {
		// Session resolves server-side from the UTC instant, so preview from that.
		const d = inputToUTCDate(liveEntryAt);
		if (d) return sessionForHour(d.getUTCHours() + d.getUTCMinutes() / 60);
		return sessionForUTC(new Date());
	});
	// Session preview parsed from the literal entry stamp (server resolves
	// the same naive-UTC value, so this preview always matches).
	const backfillSession = $derived.by(() => {
		const d = inputToUTCDate(entryAt);
		if (!d) return null;
		return sessionForHour(d.getUTCHours() + d.getUTCMinutes() / 60);
	});

	const num = (v: string): number | null => {
		const n = parseFloat(v);
		return v.trim() === '' || Number.isNaN(n) ? null : n;
	};

	// The contract comes from the server's registry — the same table the
	// backend prices every trade from. An unregistered symbol has no
	// contract, so it has no risk to show.
	const spec = $derived(specFor(symbol, $symbolMap));
	const entryN = $derived(num(entry));
	const slN = $derived(num(sl));
	const tpN = $derived(num(tp));
	const sizeN = $derived(num(size));

	// The money preview comes from the server, not from the browser: the
	// same estimator that will store the gross when the trade closes.
	let preview = $state<SymbolPreviewDto | null>(null);
	let previewToken = 0;

	$effect(() => {
		const sym = symbol.trim().toUpperCase();
		const dir = direction;
		const sz = sizeN;
		const en = entryN;
		const stop = slN;
		const target = tpN;
		if (!sym || sz === null || sz <= 0 || en === null) {
			preview = null;
			return;
		}
		const token = ++previewToken;
		const timer = setTimeout(() => {
			void previewSymbol({
				symbol: sym,
				direction: dir,
				size: sz,
				entry: en,
				sl: stop,
				exit: target
			}).then((r) => {
				if (token === previewToken) preview = r;
			});
		}, 250);
		return () => clearTimeout(timer);
	});

	// The stop distance, in the unit the trader reads it in: pips for FX,
	// points for everything else.
	const distLabel = $derived.by(() => {
		if (preview === null || !preview.registered) return null;
		if (preview.category === 'fx' && preview.risk_pips !== null) {
			return `${preview.risk_pips} pips`;
		}
		if (preview.risk_distance !== null) return `${preview.risk_distance} pts`;
		return null;
	});

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
		let liveEntryIso: string | undefined;
		if (liveEntryAt.trim()) {
			const iso = toSubmitTime(liveEntryAt, 'Entry time');
			if (iso === null) return;
			liveEntryIso = iso;
		}
		await submitOpen({
			symbol: symbol.trim(),
			direction,
			size: sizeN,
			entry_price: entryN,
			initial_sl: slN,
			tp: tpN,
			entry_time: liveEntryIso,
			account_id: accountSel ? Number(accountSel) : null,
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
			formError = `Entry and exit date/time are required (${$brokerOffset ? 'MT5' : 'UTC'}).`;
			return;
		}
		const entryIso = toSubmitTime(entryAt, 'Entry date/time');
		const exitIso = toSubmitTime(exitAt, 'Exit date/time');
		if (entryIso === null || exitIso === null) return;
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
			account_id: accountSel ? Number(accountSel) : null,
			tags: tags.split(/[\s,]+/).filter(Boolean)
		});
	}

	const field = 'field font-mono text-[13px]';
	const label = 'flex flex-col gap-1.5 text-[11px] font-medium tracking-[0.14em] uppercase text-dim';
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<div
	transition:fade={FADE}
	onclick={onBackdrop}
	use:dialogEscape={() => dismissLifecycle()}
	tabindex={-1}
	class="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-base/75 p-4 backdrop-blur-[3px]"
	role="dialog"
	aria-modal="true"
	aria-label="Open trade"
>
	<div transition:scale={MODAL} class="card w-full max-w-lg overflow-hidden p-0 shadow-pop">
		<div class="flex items-center gap-2.5 border-b border-line px-5 py-4">
			<span class="grid h-8 w-8 place-items-center rounded-lg bg-accent/12 text-accent">
				<Plus size={17} strokeWidth={2} aria-hidden="true" />
			</span>
			<h2 class="display text-xl text-fg">Open trade</h2>
			<button
				type="button"
				onclick={() => dismissLifecycle()}
				aria-label="Close"
				class="btn-icon ml-auto h-8 w-8"
			>
				<X size={17} strokeWidth={1.8} aria-hidden="true" />
			</button>
		</div>

	<form class="px-5 py-4" onsubmit={submit}>
			<datalist id="symbol-registry">
				{#each $symbols as s (s.id)}
					<option value={s.symbol}>{s.display}</option>
				{/each}
			</datalist>
			<div class="mb-4">
				<SegControl
					label="Entry mode"
					value={mode}
					onChange={(v) => (mode = v as 'live' | 'backfill')}
					options={[
						{ value: 'live', label: 'Live trade' },
						{ value: 'backfill', label: 'Historical / backfill' }
					]}
				/>
			</div>

			<div class="grid grid-cols-2 gap-3">
				<label class={label}>
					Symbol
					<input type="text" bind:value={symbol} list="symbol-registry" placeholder="GOLD" autocomplete="off" class="{field} uppercase" />
				</label>
				<span class={label}>
					Direction
					<span class="grid h-10 grid-cols-2 gap-1 rounded-xl border border-line bg-raised/50 p-1">
						{#each (['buy', 'sell'] as const) as d}
							<button
								type="button"
								onclick={() => (direction = d)}
								aria-pressed={direction === d}
								class="rounded-lg font-mono text-[13px] font-bold tracking-wide uppercase transition-all duration-200 ease-spring focus-visible:outline-none {direction ===
								d
									? d === 'buy'
										? 'bg-win/15 text-win inset-win'
										: 'bg-loss/15 text-loss inset-loss'
									: 'text-mut hover:text-fg'}"
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
					Take profit <span class="normal-case tracking-normal text-dim">(optional)</span>
					<input type="number" value={tp} oninput={(e) => (tp = e.currentTarget.value)} step="any" placeholder="4325.00" class={field} />
				</label>
			</div>

			<label class="{label} mt-3">
				Setup tags <span class="normal-case tracking-normal text-mut">#fvg #bos</span>
				<TagInput
					bind:value={tags}
					mode="setup"
					placeholder="#breakout"
					ariaLabel="Setup tags"
					inputClass="field font-sans text-[13px]"
				/>
			</label>

			<label class="{label} mt-3">
				Account <span class="normal-case tracking-normal text-mut">@alias · empty = unassigned</span>
				<select bind:value={accountSel} class={field}>
					<option value="">Unassigned</option>
					{#each $accounts as a (a.id)}
						<option value={String(a.id)}>@{a.alias} · {a.firm} {a.phase}</option>
					{/each}
				</select>
			</label>

			{#key mode}
				<div use:fluidHeight>
				<div in:fade={PANEL_FADE}>
					{#if mode === 'live'}
						<label class="{label} mt-3">
							Entry time ({zoneTag('UTC')}) <span class="normal-case tracking-normal text-dim">empty = now</span>
							<input type="datetime-local" value={liveEntryAt} oninput={(e) => (liveEntryAt = e.currentTarget.value)} class={field} />
							{#if timePreview(liveEntryAt)}
								<span class="num text-[11px] normal-case tracking-normal text-accent">→ {timePreview(liveEntryAt)}</span>
							{/if}
						</label>
					{/if}

					{#if mode === 'backfill'}
						<fieldset class="mt-3 rounded-xl border border-line p-3">
							<legend class="px-1 font-mono text-[10px] tracking-[0.16em] text-dim uppercase">Historical exit ({zoneTag('UTC')})</legend>
							<div class="grid grid-cols-2 gap-3">
								<label class={label}>
									Entry date/time
									<input type="datetime-local" value={entryAt} oninput={(e) => (entryAt = e.currentTarget.value)} class={field} />
									{#if timePreview(entryAt)}
										<span class="num text-[11px] normal-case tracking-normal text-accent">→ {timePreview(entryAt)}</span>
									{/if}
								</label>
								<label class={label}>
									Exit date/time
									<input type="datetime-local" value={exitAt} oninput={(e) => (exitAt = e.currentTarget.value)} class={field} />
									{#if timePreview(exitAt)}
										<span class="num text-[11px] normal-case tracking-normal text-accent">→ {timePreview(exitAt)}</span>
									{/if}
								</label>
								<label class={label}>
									Exit price
									<input type="number" value={exitPrice} oninput={(e) => (exitPrice = e.currentTarget.value)} step="any" class={field} />
								</label>
								<label class={label}>
									Net PnL {spec?.quote_currency ?? 'USD'} <span class="normal-case tracking-normal text-dim">(optional)</span>
									<input type="number" value={netPnl} oninput={(e) => (netPnl = e.currentTarget.value)} step="any" class={field} />
								</label>
							</div>
							<p class="num mt-2 text-[11px] text-dim" aria-live="polite">
								Session: <span class="font-bold text-accent">{backfillSession ?? '— pick entry time —'}</span>
							</p>
						</fieldset>
					{/if}
				</div>
				</div>
			{/key}

			<div class="mt-4 rounded-xl border border-line bg-raised/60 px-3.5 py-3" aria-live="polite">
				<p class="eyebrow">
					{mode === 'live' ? 'Risk preview' : 'Backfill preview'}
					<span class="normal-case tracking-normal text-dim">(estimate)</span>
				</p>
				{#if mode === 'live'}
					<p class="num mt-1.5 text-[11.5px] text-mut">
						Entry {liveEntryAt.trim() ? `${liveEntryAt.trim().replace('T', ' ')} UTC` : 'now'} · Session:
						<span class="font-bold text-fg">{liveSession}</span> (auto)
					</p>
				{/if}
				{#if symbol.trim() && spec === null}
					<p class="num mt-1.5 text-[11.5px] text-loss">
						{symbol.trim().toUpperCase()} has no contract registered — it cannot be priced.
					</p>
				{:else if preview !== null && preview.registered}
					<p class="num mt-1.5 text-[11.5px] text-dim">
						{preview.display} · {preview.contract_size} per lot · 1 pip = {preview.pip_size}
					</p>
				{/if}
				{#if preview !== null && preview.registered && preview.initial_risk !== null}
					<div class="num mt-1.5 flex flex-wrap items-baseline gap-x-2.5 gap-y-1 text-sm">
						<span>
							Risk <span class="font-bold text-loss">{fmtMoney(preview.initial_risk)}</span>
						</span>
						{#if distLabel !== null}
							<span class="text-dim">{distLabel}</span>
						{/if}
						{#if preview.gross_pnl_usd !== null}
							<span class="text-dim">
								Reward {fmtMoney(preview.gross_pnl_usd)}{#if preview.quote_currency !== 'USD' && preview.gross_pnl !== null}
									<span class="text-dim/70">({fmtCurrency(preview.gross_pnl, preview.quote_currency)})</span>
								{/if}
							</span>
						{/if}
						{#if preview.r_multiple !== null}
							<span class="font-bold text-win">{preview.r_multiple.toFixed(2)}R</span>
						{/if}
					</div>
				{:else}
					<p class="mt-1.5 text-[13px] text-dim">Type entry, stop and size to preview risk.</p>
				{/if}
				{#if !slSideOk}
					<p class="mt-1.5 text-[13px] font-medium text-loss">Stop is on the wrong side of entry for a {direction}.</p>
				{/if}
			</div>

			{#if formError}
				<p class="mt-3 text-[13px] font-medium text-loss" role="alert">{formError}</p>
			{/if}

			<div class="mt-5 flex justify-end gap-2 border-t border-line pt-4">
				<button type="button" onclick={() => dismissLifecycle()} class="btn btn-ghost h-10 px-4 text-sm">
					Cancel
				</button>
				<button type="submit" disabled={$lifecycleBusy} class="btn btn-primary h-10 px-5 text-sm">
					{$lifecycleBusy ? (mode === 'live' ? 'Opening…' : 'Saving…') : mode === 'live' ? 'Open trade' : 'Backfill trade'}
				</button>
			</div>
		</form>
	</div>
</div>
