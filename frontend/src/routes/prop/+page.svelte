<script lang="ts">
	import { onMount } from 'svelte';
	import { Pencil, Plus, Trash2, TriangleAlert, X } from 'lucide-svelte';
	import { fade, scale } from 'svelte/transition';
	import PageHead from '$lib/components/PageHead.svelte';
	import StateBlock from '$lib/components/StateBlock.svelte';
	import { api, errMsg, type CashEntryDto, type CashSummaryDto } from '$lib/api';
	import { toasts } from '$lib/stores/toast';
	import { fmtCurrency, fmtDate } from '$lib/utils/format';
	import { FADE, MODAL } from '$lib/utils/transitions';
	import { dialogLayer } from '$lib/utils/dialogs';

	const KINDS = [
		{ value: 'evaluation', label: 'Evaluation', inflow: false },
		{ value: 'reset', label: 'Reset', inflow: false },
		{ value: 'activation', label: 'Activation', inflow: false },
		{ value: 'platform_fee', label: 'Platform fee', inflow: false },
		{ value: 'refund', label: 'Refund', inflow: true },
		{ value: 'payout', label: 'Payout', inflow: true }
	] as const;
	const KIND_META: Record<string, { label: string; inflow: boolean }> = Object.fromEntries(
		KINDS.map((kind) => [kind.value, { label: kind.label, inflow: kind.inflow }])
	);

	let entries = $state<CashEntryDto[]>([]);
	let summary = $state<CashSummaryDto | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let modal = $state<null | { editing: CashEntryDto | null }>(null);
	let saving = $state(false);
	let formError = $state<string | null>(null);
	let deleteArmed = $state<CashEntryDto | null>(null);

	let fFirm = $state('');
	let fKind = $state('evaluation');
	let fAmount = $state('');
	let fCurrency = $state('USD');
	let fOccurredOn = $state('');
	let fNote = $state('');

	const field = 'field font-mono text-[13px]';
	const label = 'flex flex-col gap-1 text-[11px] font-medium tracking-[0.14em] uppercase text-dim';

	const firmNames = $derived(
		[...new Set(entries.map((entry) => entry.firm))].sort((a, b) => a.localeCompare(b))
	);
	const firmCount = $derived(summary?.by_firm.length ?? firmNames.length);
	const pageMeta = $derived(
		entries.length === 0
			? 'No cash movements yet'
			: `${entries.length} movement${entries.length === 1 ? '' : 's'} · ${firmCount} firm${firmCount === 1 ? '' : 's'}`
	);

	function kindMeta(kind: string): { label: string; inflow: boolean } {
		return KIND_META[kind] ?? { label: kind, inflow: false };
	}

	function sortEntries(rows: CashEntryDto[]): CashEntryDto[] {
		return [...rows].sort(
			(a, b) => b.occurred_on.localeCompare(a.occurred_on) || b.id - a.id
		);
	}

	function todayKey(): string {
		const parts = new Intl.DateTimeFormat('en-GB', {
			timeZone: 'Asia/Kolkata',
			year: 'numeric',
			month: '2-digit',
			day: '2-digit'
		}).formatToParts(new Date());
		const part = (type: string) => parts.find((item) => item.type === type)?.value ?? '';
		return `${part('year')}-${part('month')}-${part('day')}`;
	}

	function num(v: string | number | null | undefined): number | null {
		if (v === null || v === undefined) return null;
		if (typeof v === 'number') return Number.isFinite(v) ? v : NaN;
		if (v.trim() === '') return null;
		const n = Number(v);
		return Number.isFinite(n) ? n : NaN;
	}

	function signedMoney(amount: number, currency: string, kind: string): string {
		const body = fmtCurrency(amount, currency).replace(/^[+-]/, '');
		return `${kindMeta(kind).inflow ? '+' : '−'}${body}`;
	}

	function money(amount: number, currency: string): string {
		return fmtCurrency(amount, currency).replace(/^\+/, '');
	}

	function roiLabel(roi: number | null): string {
		return roi === null ? '—' : `${roi.toFixed(2)}×`;
	}

	function netTone(net: number): string {
		if (net > 0) return 'text-win';
		if (net < 0) return 'text-loss';
		return 'text-mut';
	}

	function convertedLabel(entry: CashEntryDto, currency: string): string | null {
		if (entry.amount_usd === null) return null;
		return signedMoney(entry.amount_usd, currency, entry.kind);
	}

	function deleteLabel(entry: CashEntryDto): string {
		return `${kindMeta(entry.kind).label} on ${fmtDate(entry.occurred_on)} for ${entry.firm}`;
	}

	async function loadLedger(): Promise<void> {
		loading = true;
		error = null;
		try {
			const [rows, totals] = await Promise.all([api.listCash(), api.cashSummary()]);
			entries = sortEntries(rows);
			summary = totals;
		} catch (err) {
			error = errMsg(err);
		} finally {
			loading = false;
		}
	}

	async function refreshSummary(): Promise<void> {
		try {
			summary = await api.cashSummary();
		} catch (err) {
			toasts.push('error', `Totals failed to refresh — ${errMsg(err)}`);
		}
	}

	onMount(() => {
		void loadLedger();
	});

	function openCreate(): void {
		fFirm = firmNames[0] ?? '';
		fKind = 'evaluation';
		fAmount = '';
		fCurrency = 'USD';
		fOccurredOn = todayKey();
		fNote = '';
		formError = null;
		deleteArmed = null;
		modal = { editing: null };
	}

	function openEdit(entry: CashEntryDto): void {
		fFirm = entry.firm;
		fKind = entry.kind;
		fAmount = String(entry.amount);
		fCurrency = entry.currency;
		fOccurredOn = entry.occurred_on;
		fNote = entry.note ?? '';
		formError = null;
		deleteArmed = null;
		modal = { editing: entry };
	}

	async function submit(event: SubmitEvent): Promise<void> {
		event.preventDefault();
		formError = null;
		const firm = fFirm.trim();
		if (!firm) {
			formError = 'Firm is required.';
			return;
		}
		if (!KIND_META[fKind]) {
			formError = 'Choose a valid cash kind.';
			return;
		}
		const amount = num(fAmount);
		if (amount === null || !Number.isFinite(amount) || amount <= 0) {
			formError = 'Amount must be a positive number.';
			return;
		}
		const currency = fCurrency.trim().toUpperCase();
		if (!/^[A-Za-z]{3,5}$/.test(currency)) {
			formError = 'Currency must be a 3-5 letter code (e.g. USD, EUR).';
			return;
		}
		if (!fOccurredOn) {
			formError = 'Choose the date the money moved.';
			return;
		}

		const editing = modal?.editing ?? null;
		const payload = {
			firm,
			kind: fKind,
			amount,
			currency,
			occurred_on: fOccurredOn,
			note: fNote.trim() || null
		};
		saving = true;
		try {
			if (editing) {
				const updated = await api.updateCash(editing.id, payload);
				entries = sortEntries(entries.map((entry) => (entry.id === updated.id ? updated : entry)));
				toasts.push('success', `Updated ${kindMeta(updated.kind).label.toLowerCase()} for ${updated.firm}.`);
			} else {
				const created = await api.createCash(payload);
				entries = sortEntries([...entries, created]);
				toasts.push('success', `Added ${kindMeta(created.kind).label.toLowerCase()} for ${created.firm}.`);
			}
			await refreshSummary();
			modal = null;
		} catch (err) {
			formError = errMsg(err);
		} finally {
			saving = false;
		}
	}

	function requestDelete(entry: CashEntryDto): void {
		if (deleteArmed?.id === entry.id) {
			void doDelete(entry);
			return;
		}
		deleteArmed = entry;
	}

	async function doDelete(entry: CashEntryDto): Promise<void> {
		try {
			await api.deleteCash(entry.id);
			entries = entries.filter((row) => row.id !== entry.id);
			await refreshSummary();
			deleteArmed = null;
			toasts.push('success', `Deleted ${kindMeta(entry.kind).label.toLowerCase()} for ${entry.firm}.`);
		} catch (err) {
			toasts.push('error', `Delete failed — ${errMsg(err)}`);
		}
	}
</script>

<svelte:head>
	<title>Prop cash · Trading Journal</title>
</svelte:head>

<PageHead eyebrow="workspace" title="Prop cash" meta={pageMeta}>
	<button type="button" onclick={openCreate} class="btn btn-primary h-10 px-4 text-sm">
		<Plus size={16} strokeWidth={2.2} aria-hidden="true" />
		Add entry
	</button>
</PageHead>

{#if loading}
	<div class="space-y-3" aria-label="Loading cash entries" role="status">
		<div class="skeleton h-14"></div>
		<div class="skeleton h-14"></div>
		<div class="skeleton h-14"></div>
	</div>
{:else if error}
	<StateBlock
		kind="error"
		title="Couldn't load the cash ledger"
		body="{error} — start the API and retry."
		actionLabel="Retry"
		onAction={() => void loadLedger()}
	/>
{:else if entries.length === 0}
	<StateBlock
		title="No cash movements yet"
		body="Record the evaluation fee that started your first challenge, then log payouts and refunds as the money moves."
		actionLabel="Add entry"
		onAction={openCreate}
	/>
{:else}
	{#if summary}
		<section class="mb-5" aria-label="Prop cash totals">
			<!-- Lead metric: the net number is the only large figure on the page. -->
			<div class="card relative overflow-hidden p-5">
				<span
					class="pointer-events-none absolute inset-0 {summary.net > 0
						? 'kpi-glow-win'
						: summary.net < 0
							? 'kpi-glow-loss'
							: ''}"
					aria-hidden="true"
				></span>
				<div class="relative flex flex-wrap items-start justify-between gap-x-3 gap-y-1">
					<div class="min-w-0">
						<p class="eyebrow">Net cash</p>
						<p class="display mt-2.5 text-[2.2rem] leading-none tabular-nums wrap-break-word {netTone(summary.net)} sm:text-[2.5rem] md:text-[2.6rem] xl:text-[2.8rem]">
							{fmtCurrency(summary.net, summary.currency)}
						</p>
						<p class="mt-2 text-[11.5px] leading-relaxed text-dim">
							Received minus spent across {summary.by_firm.length} firm{summary.by_firm.length === 1 ? '' : 's'}.
						</p>
					</div>
					<span class="num shrink-0 rounded-md border border-line bg-raised/60 px-1.5 py-0.5 text-[10px] tracking-[0.12em] text-mut uppercase">
						{summary.currency}
					</span>
				</div>
			</div>

			<!-- Supporting metrics: quiet, on the page canvas, no second hero card. -->
			<div class="mt-3 grid grid-cols-3 gap-x-4 gap-y-3 border-t border-line pt-3">
				<div class="min-w-0">
					<p class="eyebrow">Spent</p>
					<p class="num mt-1 truncate text-lg font-semibold text-fg">{money(summary.spent, summary.currency)}</p>
					<p class="mt-0.5 text-[10.5px] text-dim">Fees, resets &amp; activation</p>
				</div>
				<div class="min-w-0">
					<p class="eyebrow">Received</p>
					<p class="num mt-1 truncate text-lg font-semibold text-fg">{money(summary.received, summary.currency)}</p>
					<p class="mt-0.5 text-[10.5px] text-dim">Payouts + refunds</p>
				</div>
				<div class="min-w-0">
					<p class="eyebrow">ROI</p>
					<p class="num mt-1 truncate text-lg font-semibold text-fg">{roiLabel(summary.roi)}</p>
					<p class="mt-0.5 text-[10.5px] text-dim">Received ÷ spent</p>
				</div>
			</div>
			{#if summary.unpriced > 0}
				<p class="mt-2 flex items-start gap-1.5 px-1 text-[11px] text-accent">
					<TriangleAlert size={13} class="mt-px shrink-0" aria-hidden="true" />
					<span>
						{summary.unpriced} unpriced movement{summary.unpriced === 1 ? '' : 's'} excluded from these totals —
						add an FX rate for the missing date.
					</span>
				</p>
			{/if}
		</section>

		<section class="cq mb-5" aria-labelledby="firm-net-title">
			<div class="mb-2 flex items-center justify-between gap-3 px-1">
				<h2 id="firm-net-title" class="eyebrow">Net by firm</h2>
				<span class="num text-[10px] tracking-[0.1em] text-dim uppercase">{summary.currency}</span>
			</div>
			<!-- One firm stays a compact row; several form a balanced grid. -->
			<div class="firm-strip">
				{#each summary.by_firm as firm (firm.firm)}
					<div class="card flex min-w-0 items-center justify-between gap-3 px-3.5 py-2.5">
						<div class="min-w-0">
							<p class="truncate text-[12.5px] font-semibold text-fg" title={firm.firm}>{firm.firm}</p>
							<p class="num mt-0.5 truncate text-[10px] text-dim">
								{firm.entries} entr{firm.entries === 1 ? 'y' : 'ies'} · ROI
								<span class="text-mut">{roiLabel(firm.roi)}</span>
								{#if firm.unpriced > 0}
									<span class="text-accent">· {firm.unpriced} unpriced</span>
								{/if}
							</p>
						</div>
						<p class="num shrink-0 whitespace-nowrap text-[15px] font-semibold {netTone(firm.net)}">
							{fmtCurrency(firm.net, summary.currency)}
						</p>
					</div>
				{/each}
			</div>
		</section>
	{/if}

	{#if deleteArmed}
		<div class="card mb-4 border-loss/35 bg-loss/6 p-3 sm:p-4" role="alert">
			<div class="flex flex-wrap items-center gap-x-3 gap-y-2">
				<TriangleAlert size={16} class="shrink-0 text-loss" aria-hidden="true" />
				<p class="min-w-0 flex-1 text-[12.5px] text-fg">
					Delete <span class="num">{kindMeta(deleteArmed.kind).label.toLowerCase()}</span>
					on <span class="num">{fmtDate(deleteArmed.occurred_on)}</span> for
					<span class="font-medium">{deleteArmed.firm}</span>? This cannot be undone.
				</p>
				<div class="flex items-center gap-2">
					<button type="button" onclick={() => (deleteArmed = null)} class="btn btn-ghost h-9 px-3 text-[12px]">
						Cancel
					</button>
					<button type="button" onclick={() => deleteArmed && void doDelete(deleteArmed)} class="btn btn-danger h-9 px-3 text-[12px]">
						Delete
					</button>
				</div>
			</div>
		</div>
	{/if}

	<section class="card overflow-hidden" aria-labelledby="cash-movements-title">
		<div class="flex items-center justify-between gap-3 border-b border-line px-4 py-3 sm:px-5">
			<div class="min-w-0">
				<h2 id="cash-movements-title" class="eyebrow">Cash movements</h2>
				<p class="num mt-1 text-[11px] text-dim">Newest first</p>
			</div>
			<span class="rounded-lg bg-raised px-2 py-1 font-mono text-[10px] font-semibold tracking-[0.12em] text-mut uppercase">
				{entries.length} rows
			</span>
		</div>

		<div class="hidden overflow-x-auto md:block">
			<table class="w-full min-w-[900px] table-fixed text-left" aria-label="Prop cash entries">
				<colgroup>
					<col class="w-[110px]" />
					<col class="w-[150px]" />
					<col class="w-[125px]" />
					<col class="w-[135px]" />
					<col class="w-[135px]" />
					<col />
					<col class="w-[88px]" />
				</colgroup>
				<thead>
					<tr class="border-b border-line bg-raised/40">
						<th class="px-4 py-2.5 text-left font-mono text-[10px] font-medium tracking-[0.14em] text-dim uppercase">Date</th>
						<th class="px-3 py-2.5 text-left font-mono text-[10px] font-medium tracking-[0.14em] text-dim uppercase">Firm</th>
						<th class="px-3 py-2.5 text-left font-mono text-[10px] font-medium tracking-[0.14em] text-dim uppercase">Kind</th>
						<th class="px-3 py-2.5 text-right font-mono text-[10px] font-medium tracking-[0.14em] text-dim uppercase">Amount</th>
						<th class="px-3 py-2.5 text-right font-mono text-[10px] font-medium tracking-[0.14em] text-dim uppercase">{summary?.currency ?? 'USD'}</th>
						<th class="px-3 py-2.5 text-left font-mono text-[10px] font-medium tracking-[0.14em] text-dim uppercase">Note</th>
						<th class="px-4 py-2.5 text-right font-mono text-[10px] font-medium tracking-[0.14em] text-dim uppercase">Actions</th>
					</tr>
				</thead>
				<tbody>
					{#each entries as entry (entry.id)}
						{@const meta = kindMeta(entry.kind)}
						<tr class="border-b border-line transition-colors last:border-b-0 hover:bg-raised/35">
							<td class="whitespace-nowrap px-4 py-3 num text-[12px] text-mut">{fmtDate(entry.occurred_on)}</td>
							<td class="px-3 py-3">
								<span class="block truncate text-[12.5px] font-medium text-fg" title={entry.firm}>{entry.firm}</span>
							</td>
							<td class="px-3 py-3">
								<span class="inline-flex rounded-lg px-2 py-0.5 font-mono text-[10px] font-semibold tracking-[0.1em] uppercase {meta.inflow ? 'bg-win/12 text-win' : 'bg-loss/12 text-loss'}">
									{meta.label}
								</span>
							</td>
							<td class="whitespace-nowrap px-3 py-3 text-right num text-[12.5px] font-semibold {meta.inflow ? 'text-win' : 'text-loss'}">
								{signedMoney(entry.amount, entry.currency, entry.kind)}
							</td>
							<td class="whitespace-nowrap px-3 py-3 text-right">
								{#if entry.fx_missing}
									<span class="inline-flex items-center gap-1 text-[11px] text-accent" title="No usable FX rate on this date">
										<TriangleAlert size={12} strokeWidth={2} aria-hidden="true" />
										Unpriced
									</span>
								{:else}
									<span class="num text-[12px] text-mut">{convertedLabel(entry, summary?.currency ?? 'USD')}</span>
								{/if}
							</td>
							<td class="px-3 py-3">
								<span class="block truncate text-[12px] text-dim" title={entry.note ?? ''}>{entry.note ?? '—'}</span>
							</td>
							<td class="px-4 py-3">
								<div class="flex items-center justify-end gap-1">
									<button
										type="button"
										onclick={() => openEdit(entry)}
										aria-label="Edit {deleteLabel(entry)}"
										class="btn-icon h-8 w-8"
									>
										<Pencil size={14} strokeWidth={1.8} aria-hidden="true" />
									</button>
									<button
										type="button"
										onclick={() => requestDelete(entry)}
										aria-label="Delete {deleteLabel(entry)}"
										class="btn-icon h-8 w-8 text-loss {deleteArmed?.id === entry.id ? 'bg-loss/12' : ''}"
									>
										<Trash2 size={14} strokeWidth={1.8} aria-hidden="true" />
									</button>
								</div>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>

		<div class="divide-y divide-line md:hidden" aria-label="Cash entries">
			{#each entries as entry (entry.id)}
				{@const meta = kindMeta(entry.kind)}
				<article class="p-4">
					<div class="flex items-start gap-3">
						<div class="min-w-0 flex-1">
							<p class="truncate text-[13px] font-semibold text-fg">{entry.firm}</p>
							<p class="num mt-1 text-[11px] text-dim">{fmtDate(entry.occurred_on)}</p>
						</div>
						<span class="inline-flex shrink-0 rounded-lg px-2 py-0.5 font-mono text-[10px] font-semibold tracking-[0.1em] uppercase {meta.inflow ? 'bg-win/12 text-win' : 'bg-loss/12 text-loss'}">
							{meta.label}
						</span>
					</div>
					<div class="mt-3 flex flex-wrap items-baseline justify-between gap-2">
						<span class="num text-[15px] font-semibold {meta.inflow ? 'text-win' : 'text-loss'}">
							{signedMoney(entry.amount, entry.currency, entry.kind)}
						</span>
						{#if entry.fx_missing}
							<span class="inline-flex items-center gap-1 text-[11px] text-accent">
								<TriangleAlert size={12} strokeWidth={2} aria-hidden="true" />
								Unpriced
							</span>
						{:else}
							<span class="num text-[11px] text-dim">{convertedLabel(entry, summary?.currency ?? 'USD')} {summary?.currency ?? 'USD'}</span>
						{/if}
					</div>
					{#if entry.note}
						<p class="mt-2 truncate text-[12px] text-dim" title={entry.note}>{entry.note}</p>
					{/if}
					<div class="mt-3 flex items-center justify-end gap-1.5 border-t border-line pt-2.5">
						<button type="button" onclick={() => openEdit(entry)} aria-label="Edit {deleteLabel(entry)}" class="btn-icon h-8 w-8">
							<Pencil size={14} strokeWidth={1.8} aria-hidden="true" />
						</button>
						<button
							type="button"
							onclick={() => requestDelete(entry)}
							aria-label="Delete {deleteLabel(entry)}"
							class="btn-icon h-8 w-8 text-loss {deleteArmed?.id === entry.id ? 'bg-loss/12' : ''}"
						>
							<Trash2 size={14} strokeWidth={1.8} aria-hidden="true" />
						</button>
					</div>
				</article>
			{/each}
		</div>
	</section>
{/if}

{#if modal}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<div
		transition:fade={FADE}
		onclick={(event) => event.target === event.currentTarget && (modal = null)}
		use:dialogLayer={() => (modal = null)}
		tabindex={-1}
		class="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-base/75 p-4 backdrop-blur-[3px] sm:items-center sm:p-6"
		role="dialog"
		aria-modal="true"
		aria-label={modal.editing ? 'Edit cash entry' : 'Add cash entry'}
	>
		<div transition:scale={MODAL} class="card flex max-h-[calc(100dvh-2rem)] w-full max-w-lg flex-col overflow-hidden p-0 shadow-pop">
			<div class="flex shrink-0 items-center gap-2.5 border-b border-line px-5 py-4">
				<h2 class="display text-xl text-fg">{modal.editing ? 'Edit cash entry' : 'Add cash entry'}</h2>
				<button type="button" onclick={() => (modal = null)} aria-label="Close" class="btn-icon ml-auto h-8 w-8">
					<X size={17} strokeWidth={1.8} aria-hidden="true" />
				</button>
			</div>
			<form class="flex min-h-0 flex-1 flex-col" onsubmit={submit}>
				<div class="min-h-0 flex-1 overflow-y-auto px-5 py-4">
					<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
					<label class="{label} sm:col-span-2">
						Firm
						<input
							type="text"
							bind:value={fFirm}
							list="cash-firm-options"
							placeholder="FTMO"
							autocomplete="off"
							required
							class={field}
						/>
					</label>
					<label class={label}>
						Kind
						<select bind:value={fKind} class={field}>
							{#each KINDS as kind}
								<option value={kind.value}>{kind.label}</option>
							{/each}
						</select>
					</label>
					<label class={label}>
						Amount
						<input type="number" bind:value={fAmount} min="0.01" step="any" placeholder="540" required class={field} />
					</label>
					<label class={label}>
						Currency
						<input type="text" bind:value={fCurrency} maxlength={5} placeholder="USD" autocomplete="off" required class="{field} uppercase" />
					</label>
					<label class={label}>
						Date moved
						<input type="date" bind:value={fOccurredOn} required class={field} />
					</label>
					<label class="{label} sm:col-span-2">
						Note <span class="normal-case tracking-normal text-dim">(optional)</span>
						<textarea bind:value={fNote} rows="3" placeholder="FTMO 100k challenge — reset after breach" class="field h-24 resize-y py-2 font-mono text-[13px]"></textarea>
					</label>
				</div>
				<datalist id="cash-firm-options">
					{#each firmNames as firm}
						<option value={firm}></option>
					{/each}
				</datalist>
				<p class="num mt-3 text-[11px] text-dim">Amount is always positive. The kind decides whether it is money in or money out.</p>
				{#if formError}<p class="mt-3 text-[13px] font-medium text-loss" role="alert">{formError}</p>{/if}
				</div>
				<div class="flex shrink-0 justify-end gap-2 border-t border-line px-5 py-4">
					<button type="button" onclick={() => (modal = null)} class="btn btn-ghost h-10 px-4 text-sm">Cancel</button>
					<button type="submit" disabled={saving} class="btn btn-primary h-10 px-5 text-sm">
						{saving ? 'Saving…' : modal.editing ? 'Save entry' : 'Add entry'}
					</button>
				</div>
			</form>
		</div>
	</div>
{/if}
