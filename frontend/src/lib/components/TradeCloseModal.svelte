<script lang="ts">
	import { Flag, X } from 'lucide-svelte';
	import { fade, scale } from 'svelte/transition';
	import { dismissLifecycle, lifecycleBusy, submitClose, trades } from '$lib/stores/trades';
	import { fmtMoney, fmtR } from '$lib/utils/format';
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
		await submitClose(trade.id, {
			exit_price: exitN,
			gross_pnl: grossN,
			fees: feesN ?? 0,
			timestamp_close: exitAt.trim() ? `${exitAt.trim()}:00` : undefined,
			mistake_tags: mistakes.split(/[\s,]+/).filter(Boolean),
			review_notes: notes.trim() || null
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
	aria-label="Close trade"
>
	<div transition:scale={MODAL} class="w-full max-w-lg rounded-2xl border border-slate-200 bg-white shadow-pop dark:border-white/[0.08] dark:bg-surface-900">
		<div class="flex items-center gap-2 border-b border-slate-200 px-5 py-4 dark:border-white/[0.07]">
			<Flag size={16} strokeWidth={2} aria-hidden="true" class="text-rose-500" />
			<h2 class="text-sm font-semibold tracking-tight">
				Close {trade ? `${(trade.direction ?? '').toUpperCase()} ${trade.symbol ?? ''}` : 'trade'}
			</h2>
			<button
				type="button"
				onclick={() => dismissLifecycle()}
				aria-label="Close"
				class="ml-auto grid h-8 w-8 place-items-center rounded-lg text-slate-400 transition-all hover:bg-slate-100 hover:text-slate-700 focus-visible:outline-emerald-500 active:scale-95 dark:hover:bg-white/[0.06] dark:hover:text-slate-200"
			>
				<X size={17} strokeWidth={1.8} aria-hidden="true" />
			</button>
		</div>

		{#if !trade}
			<p class="px-5 py-8 text-center text-sm text-slate-500">Trade not found — it may have been deleted.</p>
		{:else if trade.status !== 'OPEN'}
			<p class="px-5 py-8 text-center text-sm text-slate-500">
				This trade is already {trade.status.toLowerCase()}.
			</p>
		{:else}
			<form class="px-5 py-4" onsubmit={submit}>
				<p class="mb-3 font-mono text-xs tabular-nums text-slate-500 dark:text-slate-400">
					Entry {trade.entry_price ?? '—'} · SL {trade.initial_sl ?? '—'} · {trade.ticket}
				</p>
				<div class="grid grid-cols-2 gap-3 sm:grid-cols-3">
					<label class={label}>
						Exit price
						<input type="number" value={exit} oninput={(e) => (exit = e.currentTarget.value)} step="any" class={field} />
					</label>
					<label class={label}>
						Gross PnL <span class="font-normal opacity-70">(optional)</span>
						<input type="number" value={gross} oninput={(e) => (gross = e.currentTarget.value)} step="any" placeholder="+135" class={field} />
					</label>
					<label class={label}>
						Broker fees
						<input type="number" value={fees} oninput={(e) => (fees = e.currentTarget.value)} min="0" step="any" class={field} />
					</label>
					<label class={label}>
						Exit time (UTC) <span class="font-normal opacity-70">empty = now</span>
						<input type="datetime-local" value={exitAt} oninput={(e) => (exitAt = e.currentTarget.value)} class={field} />
					</label>
				</div>
				<label class="{label} mt-3">
					Mistake tags <span class="font-mono font-normal">!early !fomo</span>
					<input type="text" bind:value={mistakes} placeholder="!early" autocomplete="off" class="{field} font-sans" />
				</label>
				<label class="{label} mt-3">
					Reflection notes
					<textarea
						bind:value={notes}
						rows={3}
						placeholder="What did you learn?"
						class="resize-y rounded-lg border border-slate-200 bg-transparent p-2.5 text-sm leading-relaxed outline-none placeholder:text-slate-400 focus:border-emerald-500 dark:border-white/10"
					></textarea>
				</label>

				<div class="mt-4 rounded-xl border border-slate-200 bg-slate-50/70 px-3.5 py-3 dark:border-white/[0.07] dark:bg-white/[0.02]" aria-live="polite">
					<p class="font-mono text-[11px] tracking-wider text-slate-400 uppercase">Close preview</p>
					<p class="mt-1 font-mono text-sm tabular-nums">
						Net <span class="font-bold">{netPreview === null ? '—' : fmtMoney(netPreview)}</span>
						<span class="text-slate-500 dark:text-slate-400"> · </span>R <span class="font-bold">{rPreview === null ? '—' : fmtR(rPreview)}</span>
					</p>
					<p class="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">
						Preview only — the server computes the stored values. Invalid exit/SL data clears R.
					</p>
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
						class="h-10 rounded-lg bg-rose-500 px-5 text-sm font-semibold text-white shadow-pop transition-all duration-150 hover:bg-rose-600 focus-visible:outline-rose-500 active:scale-[0.98] disabled:cursor-wait disabled:opacity-70"
					>
						{$lifecycleBusy ? 'Closing…' : 'Close trade'}
					</button>
				</div>
			</form>
		{/if}
	</div>
</div>
