<script lang="ts">
	import { Flag, X } from 'lucide-svelte';
	import { untrack } from 'svelte';
	import { fade, scale } from 'svelte/transition';
	import { dismissLifecycle, ensureTrade, lifecycleBusy, submitClose, tradeCache } from '$lib/stores/trades';
	import TagInput from '$lib/components/TagInput.svelte';
	import { fmtCurrency, fmtMoney, fmtR, mt5WallToUTC, pnlTone, previewIST, previewMT5, rTone, toneText } from '$lib/utils/format';
	import { brokerOffset } from '$lib/stores/broker';
	import { loadSymbols, specFor, symbolMap } from '$lib/stores/symbols';
	import { FADE, MODAL } from '$lib/utils/transitions';
	import { dialogLayer } from '$lib/utils/dialogs';
	import { onMount } from 'svelte';

	const { tradeId }: { tradeId: number } = $props();

	onMount(() => {
		void loadSymbols();
	});

	const trade = $derived($tradeCache.get(tradeId) ?? null);

	// The trade may live on another page of the ledger — fetch it by id.
	$effect(() => {
		void ensureTrade(tradeId);
	});
	// The contract comes from the server's registry — never a local guess.
	const spec = $derived(trade ? specFor(trade.symbol ?? '', $symbolMap) : null);

	let exit = $state('');
	let gross = $state('');
	let fees = $state('');
	let mistakes = $state('');
	let notes = $state('');
	// Explicit exit (UTC); empty = now.
	let exitAt = $state('');
	let formError = $state<string | null>(null);

	// Prefill once per trade. The form fields are read untracked on purpose:
	// reading them made this effect re-run the moment the user cleared the
	// exit price and put the entry price straight back, so submitting an
	// untouched form booked a 0 P&L trade instead of asking for an exit.
	const tradeIdOf = $derived(trade?.id ?? null);
	let prefilledFor = $state<number | null>(null);

	$effect(() => {
		const id = tradeIdOf;
		if (id === null) return;
		untrack(() => {
			if (prefilledFor === id) return;
			prefilledFor = id;
			const entry = trade?.entry_price;
			if (entry !== null && entry !== undefined) exit = String(entry);
			fees = String(trade?.fees ?? 0);
		});
	});

	const num = (v: string): number | null => {
		const n = parseFloat(v);
		return v.trim() === '' || Number.isNaN(n) ? null : n;
	};

	const exitN = $derived(num(exit));
	const grossN = $derived(num(gross));
	const feesN = $derived(num(fees) ?? 0);

	const netPreview = $derived(grossN !== null ? grossN - (feesN ?? 0) : null);
	// The projected R is built from the server's own numbers: the risk the
	// trade actually carried (realized_risk) and the registry's contract
	// size. No local re-derivation of the stop rule.
	const rPreview = $derived.by(() => {
		if (!trade || exitN === null || trade.entry_price === null) return null;
		const sign = (trade.direction ?? '').toLowerCase().startsWith('sell') ? -1 : 1;
		const move = (exitN - trade.entry_price) * sign;
		const riskMoney = trade.realized_risk ?? trade.initial_risk;
		if (
			riskMoney !== null &&
			riskMoney !== undefined &&
			riskMoney > 0 &&
			spec !== null &&
			trade.size
		) {
			const gross = move * spec.contract_size * trade.size;
			return gross / riskMoney;
		}
		// No recorded risk (a trade with no stop, or one stored before the
		// risk columns existed): fall back to the planned stop distance.
		if (trade.initial_sl === null) return null;
		const risk = Math.abs(trade.entry_price - trade.initial_sl);
		if (risk === 0) return null;
		return move / risk;
	});

	function onBackdrop(e: MouseEvent): void {
		if (e.target === e.currentTarget) dismissLifecycle();
	}

	/** Wall input → UTC `YYYY-MM-DDTHH:MM:SS` for the API (null when invalid). */
	function exitToUTC(): string | null {
		const t = exitAt.trim();
		if (!t) return null;
		if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(t)) return null;
		if ($brokerOffset) return mt5WallToUTC(t, $brokerOffset.minutes);
		return Number.isNaN(new Date(`${t}:00Z`).getTime()) ? null : `${t}:00`;
	}

	const exitPreview = (raw: string): string => {
		if ($brokerOffset) return previewMT5(raw, $brokerOffset.minutes);
		return previewIST(raw);
	};

	async function submit(e: SubmitEvent): Promise<void> {
		e.preventDefault();
		formError = null;
		if (!trade) {
			formError = 'Trade not found.';
			return;
		}
		if (trade.status !== 'OPEN') {
			formError = 'This trade is already closed.';
			return;
		}
		if (exitN === null) {
			formError = 'Exit price must be a number.';
			return;
		}
		let exitIso: string | undefined;
		if (exitAt.trim()) {
			const iso = exitToUTC();
			if (iso === null) {
				formError = 'Exit time must be a valid date/time.';
				return;
			}
			exitIso = iso;
		}
		await submitClose(trade.id, {
			exit_price: exitN,
			gross_pnl: grossN,
			fees: feesN ?? 0,
			timestamp_close: exitIso,
			mistake_tags: mistakes.split(/[\s,]+/).filter(Boolean),
			review_notes: notes.trim() || null
		});
	}

	const field = 'field font-mono text-[13px]';
	const label = 'flex flex-col gap-1.5 text-[11px] font-medium tracking-[0.14em] uppercase text-dim';
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<div
	transition:fade={FADE}
	onclick={onBackdrop}
	use:dialogLayer={() => dismissLifecycle()}
	tabindex={-1}
	class="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-base/75 p-4 backdrop-blur-[3px]"
	role="dialog"
	aria-modal="true"
	aria-label="Close trade"
>
	<div transition:scale={MODAL} class="card w-full max-w-lg overflow-hidden shadow-pop">
		<div class="flex items-center gap-2.5 border-b border-line px-5 py-4">
			<span class="grid h-8 w-8 place-items-center rounded-lg bg-loss/12 text-loss">
				<Flag size={16} strokeWidth={2} aria-hidden="true" />
			</span>
			<h2 class="display text-xl text-fg">
				Close {trade ? `${(trade.direction ?? '').toUpperCase()} ${trade.symbol ?? ''}` : 'trade'}
			</h2>
			<button
				type="button"
				onclick={() => dismissLifecycle()}
				aria-label="Close"
				class="btn-icon ml-auto h-8 w-8"
			>
				<X size={17} strokeWidth={1.8} aria-hidden="true" />
			</button>
		</div>

		{#if !trade}
			<p class="px-5 py-10 text-center text-sm text-mut">Trade not found — it may have been deleted.</p>
		{:else if trade.status !== 'OPEN'}
			<p class="px-5 py-10 text-center text-sm text-mut">
				This trade is already {trade.status.toLowerCase()}.
			</p>
		{:else}
			<form class="px-5 py-4" onsubmit={submit}>
				<p class="num mb-4 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11.5px] text-dim">
					<span>Entry <span class="text-fg">{trade.entry_price ?? '—'}</span></span>
					<span class="text-dim/60">·</span>
					<span>SL <span class="text-fg">{trade.initial_sl ?? '—'}</span></span>
					<span class="text-dim/60">·</span>
					<span>{trade.ticket}</span>
				</p>
				<div class="grid grid-cols-2 gap-3 sm:grid-cols-3">
					<label class={label}>
						Exit price
						<input type="number" value={exit} oninput={(e) => (exit = e.currentTarget.value)} step="any" class={field} />
					</label>
					<label class={label}>
						Gross PnL {trade.quote_currency} <span class="normal-case tracking-normal text-dim">(optional)</span>
						<input type="number" value={gross} oninput={(e) => (gross = e.currentTarget.value)} step="any" placeholder="+135" class={field} />
					</label>
					<label class={label}>
						Broker fees
						<input type="number" value={fees} oninput={(e) => (fees = e.currentTarget.value)} min="0" step="any" class={field} />
					</label>
					<label class="{label} col-span-2 sm:col-span-1">
						Exit time ({$brokerOffset ? `MT5 · ${$brokerOffset.label}` : 'UTC'}) <span class="normal-case tracking-normal text-dim">empty = now</span>
						<input type="datetime-local" value={exitAt} oninput={(e) => (exitAt = e.currentTarget.value)} class={field} />
						{#if exitPreview(exitAt)}
							<span class="num text-[11px] normal-case tracking-normal text-accent">→ {exitPreview(exitAt)}</span>
						{/if}
					</label>
				</div>
				<label class="{label} mt-3">
					Mistake tags <span class="normal-case tracking-normal text-mut">!early !fomo</span>
					<TagInput
						bind:value={mistakes}
						mode="mistake"
						placeholder="!early"
						ariaLabel="Mistake tags"
						inputClass="field font-sans text-[13px]"
					/>
				</label>
				<label class="{label} mt-3">
					Reflection notes
					<textarea
						bind:value={notes}
						rows={3}
						placeholder="What did you learn?"
						class="field resize-y text-[13px]"
					></textarea>
				</label>

				<div class="mt-4 rounded-xl border border-line bg-raised/60 px-3.5 py-3" aria-live="polite">
					<p class="eyebrow">Close preview</p>
					{#if spec !== null}
						<p class="num mt-1.5 text-[11.5px] text-dim">
							{spec.display} · {spec.contract_size} per lot · 1 pip = {spec.pip_size}
						</p>
					{/if}
					<p class="num mt-1.5 flex flex-wrap items-baseline gap-x-3 text-sm">
						<span>
							<span class="text-dim">Net</span>
							<span class="ml-1.5 font-bold {toneText[pnlTone(netPreview)]}">
								{netPreview === null ? '—' : fmtCurrency(netPreview, trade.quote_currency)}
							</span>
						</span>
						<span>
							<span class="text-dim">R</span>
							<span class="ml-1.5 font-bold {toneText[rTone(rPreview)]}">
								{rPreview === null ? '—' : fmtR(rPreview)}
							</span>
						</span>
						{#if trade.realized_risk !== null}
							<span>
								<span class="text-dim">Risk</span>
								<span class="ml-1.5 font-bold text-loss">{fmtMoney(trade.realized_risk)}</span>
							</span>
						{/if}
					</p>
					<p class="mt-1.5 text-[11px] leading-relaxed text-dim">
						Preview only — the server computes the stored values. Invalid exit/SL data clears R.
					</p>
				</div>

				{#if formError}
					<p class="mt-3 text-[13px] font-medium text-loss" role="alert">{formError}</p>
				{/if}

				<div class="mt-5 flex justify-end gap-2 border-t border-line pt-4">
					<button type="button" onclick={() => dismissLifecycle()} class="btn btn-ghost h-10 px-4 text-sm">
						Cancel
					</button>
					<button type="submit" disabled={$lifecycleBusy} class="btn btn-danger h-10 px-5 text-sm">
						{$lifecycleBusy ? 'Closing…' : 'Close trade'}
					</button>
				</div>
			</form>
		{/if}
	</div>
</div>
