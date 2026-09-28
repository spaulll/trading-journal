<script lang="ts">
	import { Flag, X } from 'lucide-svelte';
	import { fade, scale } from 'svelte/transition';
	import { dismissLifecycle, lifecycleBusy, submitClose, trades } from '$lib/stores/trades';
	import { fmtMoney, fmtR, mt5WallToUTC, pnlTone, previewIST, previewMT5, toneText } from '$lib/utils/format';
	import { brokerOffset } from '$lib/stores/broker';
	import { FADE, MODAL } from '$lib/utils/transitions';

	const { tradeId }: { tradeId: number } = $props();

	const trade = $derived($trades.find((t) => t.id === tradeId) ?? null);

	let exit = $state('');
	let gross = $state('');
	let fees = $state('');
	let mistakes = $state('');
	let notes = $state('');
	// Explicit exit (UTC); empty = now.
	let exitAt = $state('');
	let formError = $state<string | null>(null);

	$effect(() => {
		if (trade && exit === '' && trade.entry_price !== null) exit = String(trade.entry_price);
		if (trade && fees === '') fees = String(trade.fees ?? 0);
	});

	const num = (v: string): number | null => {
		const n = parseFloat(v);
		return v.trim() === '' || Number.isNaN(n) ? null : n;
	};

	const exitN = $derived(num(exit));
	const grossN = $derived(num(gross));
	const feesN = $derived(num(fees) ?? 0);

	const netPreview = $derived(grossN !== null ? grossN - (feesN ?? 0) : null);
	const rPreview = $derived.by(() => {
		if (!trade || exitN === null || trade.entry_price === null || trade.initial_sl === null) return null;
		const risk = Math.abs(trade.entry_price - trade.initial_sl);
		if (risk === 0) return null;
		const move =
			(trade.direction ?? '').toLowerCase().startsWith('sell')
				? trade.entry_price - exitN
				: exitN - trade.entry_price;
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

<svelte:window onkeydown={(e) => e.key === 'Escape' && dismissLifecycle()} />

<div
	transition:fade={FADE}
	onclick={onBackdrop}
	onkeydown={(e) => e.key === 'Escape' && dismissLifecycle()}
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
						Gross PnL <span class="normal-case tracking-normal text-dim">(optional)</span>
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
					<input type="text" bind:value={mistakes} placeholder="!early" autocomplete="off" class="field font-sans text-[13px]" />
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
					<p class="num mt-1.5 flex flex-wrap items-baseline gap-x-3 text-sm">
						<span>
							<span class="text-dim">Net</span>
							<span class="ml-1.5 font-bold {toneText[pnlTone(netPreview)]}">
								{netPreview === null ? '—' : fmtMoney(netPreview)}
							</span>
						</span>
						<span>
							<span class="text-dim">R</span>
							<span class="ml-1.5 font-bold {toneText[pnlTone(rPreview)]}">
								{rPreview === null ? '—' : fmtR(rPreview)}
							</span>
						</span>
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
