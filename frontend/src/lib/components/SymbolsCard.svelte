<script lang="ts">
	import { BookOpen, ChevronDown, Pencil, Plus, X } from 'lucide-svelte';
	import { fade, scale } from 'svelte/transition';
	import { api, errMsg, type SymbolSpecDto } from '$lib/api';
	import { toasts } from '$lib/stores/toast';
	import { fmtNum } from '$lib/utils/format';
	import { FADE, MODAL } from '$lib/utils/transitions';
	import { dialogLayer } from '$lib/utils/dialogs';

	let specs = $state<SymbolSpecDto[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let open = $state(false);

	// Add row
	let adding = $state(false);
	let saving = $state(false);
	let fSymbol = $state('');
	let fContract = $state('100000');
	let fPip = $state('0.01');
	let fQuote = $state('USD');
	let fCategory = $state('fx');
	let formError = $state<string | null>(null);

	const CATEGORIES = ['fx', 'metal', 'crypto', 'index', 'future'];
	const label = 'flex flex-col gap-1 text-[11px] font-medium tracking-[0.14em] uppercase text-dim';
	const field = 'field font-mono text-[13px]';

	async function load(): Promise<void> {
		loading = true;
		error = null;
		try {
			specs = await api.listSymbols(true);
		} catch (e) {
			error = errMsg(e);
		} finally {
			loading = false;
		}
	}

	void load();

	function beginAdd(): void {
		adding = true;
		formError = null;
	}

	function cancelAdd(): void {
		adding = false;
		formError = null;
	}

	async function create(): Promise<void> {
		const symbol = fSymbol.trim().toUpperCase();
		const contract = Number(fContract);
		const pip = Number(fPip);
		if (!symbol) {
			formError = 'Symbol required.';
			return;
		}
		if (!Number.isFinite(contract) || contract <= 0) {
			formError = 'Contract must be > 0.';
			return;
		}
		if (!Number.isFinite(pip) || pip <= 0) {
			formError = 'Pip must be > 0.';
			return;
		}
		saving = true;
		formError = null;
		try {
			await api.createSymbol({
				symbol,
				display: symbol,
				category: fCategory,
				contract_size: contract,
				pip_size: pip,
				quote_currency: fQuote.trim().toUpperCase() || 'USD',
				enabled: true
			});
			toasts.push('success', `${symbol} registered — future trades on it will be priced.`);
			adding = false;
			fSymbol = '';
			fContract = '100000';
			fPip = '0.01';
			fQuote = 'USD';
			fCategory = 'fx';
			await load();
		} catch (e) {
			formError = errMsg(e);
		} finally {
			saving = false;
		}
	}

	// Edit modal
	let editing = $state<SymbolSpecDto | null>(null);
	let eDisplay = $state('');
	let eCategory = $state('fx');
	let eContract = $state('');
	let ePip = $state('');
	let eQuote = $state('');
	let eEnabled = $state(true);
	let editSaving = $state(false);
	let editError = $state<string | null>(null);

	function onBackdrop(e: MouseEvent): void {
		if (e.target === e.currentTarget) cancelEdit();
	}

	function openEdit(spec: SymbolSpecDto): void {
		editing = spec;
		eDisplay = spec.display;
		eCategory = spec.category;
		eContract = String(spec.contract_size);
		ePip = String(spec.pip_size);
		eQuote = spec.quote_currency;
		eEnabled = spec.enabled;
		editError = null;
	}

	function cancelEdit(): void {
		editing = null;
		editError = null;
	}

	async function saveEdit(): Promise<void> {
		if (!editing) return;
		const contract = Number(eContract);
		const pip = Number(ePip);
		if (!Number.isFinite(contract) || contract <= 0) {
			editError = 'Contract must be > 0.';
			return;
		}
		if (!Number.isFinite(pip) || pip <= 0) {
			editError = 'Pip must be > 0.';
			return;
		}
		editSaving = true;
		editError = null;
		try {
			const updated = await api.updateSymbol(editing.id, {
				display: eDisplay.trim() || editing.symbol,
				category: eCategory,
				contract_size: contract,
				pip_size: pip,
				quote_currency: eQuote.trim().toUpperCase() || 'USD',
				enabled: eEnabled
			});
			toasts.push('success', `${updated.symbol} updated.`);
			cancelEdit();
			await load();
		} catch (e) {
			editError = errMsg(e);
		} finally {
			editSaving = false;
		}
	}
</script>

<section aria-label="Symbol contracts" class="card rise p-4">
	<button
		type="button"
		class="flex w-full items-center gap-2 text-left"
		onclick={() => (open = !open)}
		aria-expanded={open}
	>
		<BookOpen size={16} strokeWidth={2} aria-hidden="true" class="shrink-0 text-accent" />
		<h2 class="text-[15px] font-semibold text-fg">Symbol contracts</h2>
		<span class="num text-[11px] text-dim">{specs.length} registered</span>
		<ChevronDown
			size={14}
			strokeWidth={2}
			aria-hidden="true"
			class="ml-auto shrink-0 text-dim transition-transform {open ? 'rotate-180' : ''}"
		/>
	</button>

	{#if open}
		<p class="mt-1.5 text-[12px] leading-snug text-mut">
			Contracts differ per firm — add or adjust any pair here.
		</p>

		{#if adding}
			<div class="mt-3 rounded-xl border border-line bg-raised/30 p-3" aria-label="Add symbol form">
				<div class="grid grid-cols-2 gap-x-2 gap-y-2 sm:grid-cols-4">
					<label class="flex min-w-0 flex-col gap-1">
						<span class="font-mono text-[10px] tracking-[0.14em] text-dim uppercase">Symbol</span>
						<input type="text" bind:value={fSymbol} placeholder="EURTRY" class="field h-8 font-mono text-[12px]" />
					</label>
					<label class="flex min-w-0 flex-col gap-1">
						<span class="font-mono text-[10px] tracking-[0.14em] text-dim uppercase">Contract size</span>
						<input type="number" bind:value={fContract} class="field h-8 font-mono text-[12px]" />
					</label>
					<label class="flex min-w-0 flex-col gap-1">
						<span class="font-mono text-[10px] tracking-[0.14em] text-dim uppercase">Pip size</span>
						<input type="number" bind:value={fPip} step="any" class="field h-8 font-mono text-[12px]" />
					</label>
					<label class="flex min-w-0 flex-col gap-1">
						<span class="font-mono text-[10px] tracking-[0.14em] text-dim uppercase">Quote currency</span>
						<input type="text" bind:value={fQuote} placeholder="USD" class="field h-8 font-mono text-[12px]" />
					</label>
					<label class="flex min-w-0 flex-col gap-1">
						<span class="font-mono text-[10px] tracking-[0.14em] text-dim uppercase">Category</span>
						<select bind:value={fCategory} class="field h-8 text-[12px]">
							{#each CATEGORIES as c (c)}
								<option value={c}>{c}</option>
							{/each}
						</select>
					</label>
				</div>
				<div class="mt-2.5 flex flex-wrap items-center gap-2">
					<button type="button" onclick={() => void create()} disabled={saving} class="btn btn-primary h-8 px-3 text-[12px]">
						{saving ? 'Saving…' : 'Register'}
					</button>
					<button type="button" onclick={cancelAdd} disabled={saving} class="btn h-8 px-3 text-[12px]">
						Cancel
					</button>
					{#if formError}
						<span role="alert" class="num text-[11px] text-loss">{formError}</span>
					{/if}
				</div>
			</div>
		{:else}
			<div class="mt-3">
				<button type="button" onclick={beginAdd} class="btn h-8 px-3 text-[12px]">
					<Plus size={13} aria-hidden="true" class="mr-1" /> Add symbol
				</button>
				{#if error}
					<span class="num ml-2 text-[11px] text-loss">{error}</span>
				{/if}
			</div>
		{/if}

		<div class="mt-3 max-h-72 overflow-y-auto rounded-xl border border-line">
			<table class="w-full border-collapse text-left text-[12px]">
				<thead>
					<tr class="font-mono text-[10px] tracking-[0.14em] text-dim uppercase">
						<th class="border-b border-line py-1.5 pl-3 pr-2 font-medium">Symbol</th>
						<th class="border-b border-line py-1.5 pr-2 text-right font-medium">Contract</th>
						<th class="border-b border-line py-1.5 pr-2 text-right font-medium">Pip</th>
						<th class="border-b border-line py-1.5 pr-2 font-medium">Quote</th>
						<th class="border-b border-line py-1.5 pr-2 font-medium">Type</th>
						<th class="border-b border-line py-1.5 pr-3 text-right font-medium">Edit</th>
					</tr>
				</thead>
				<tbody>
					{#each specs as spec (spec.id)}
						<tr class="border-b border-line last:border-0">
							<td class="py-1.5 pl-3 pr-2">
								<span class="num font-semibold text-fg">{spec.symbol}</span>
							</td>
							<td class="py-1.5 pr-2 text-right"><span class="num text-mut">{fmtNum(spec.contract_size)}</span></td>
							<td class="py-1.5 pr-2 text-right"><span class="num text-mut">{fmtNum(spec.pip_size)}</span></td>
							<td class="py-1.5 pr-2"><span class="num text-mut">{spec.quote_currency}</span></td>
							<td class="py-1.5 pr-2">
								<span class="num text-[10px] uppercase tracking-wide {spec.enabled ? 'text-win' : 'text-dim'}">
									{spec.enabled ? 'on' : 'off'}
								</span>
							</td>
							<td class="py-1.5 pl-2 pr-3 text-right">
								<button type="button" onclick={() => openEdit(spec)} class="btn h-7 px-2 text-[11px]">
									<Pencil size={11} aria-hidden="true" class="mr-1" /> Edit
								</button>
							</td>
						</tr>
					{/each}
					{#if !loading && specs.length === 0}
						<tr>
							<td colspan="6" class="py-3 text-center text-[12px] text-dim">No symbols registered yet.</td>
						</tr>
					{/if}
				</tbody>
			</table>
			{#if loading}
				<p class="p-3 text-[11px] text-dim">Loading registry…</p>
			{/if}
		</div>
	{/if}
</section>

{#if editing}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<div
		transition:fade={FADE}
		onclick={onBackdrop}
		use:dialogLayer={() => cancelEdit()}
		tabindex={-1}
		class="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-base/75 p-4 backdrop-blur-[3px]"
		role="dialog"
		aria-modal="true"
		aria-label="Edit symbol contract"
	>
		<div transition:scale={MODAL} class="card w-full max-w-md overflow-hidden p-0 shadow-pop">
			<div class="flex items-center gap-2.5 border-b border-line px-5 py-4">
				<span class="grid h-8 w-8 place-items-center rounded-lg bg-accent/12 text-accent">
					<Pencil size={17} strokeWidth={2} aria-hidden="true" />
				</span>
				<h2 class="display text-xl text-fg">Edit {editing.symbol}</h2>
				<button type="button" onclick={() => cancelEdit()} aria-label="Close" class="btn-icon ml-auto h-8 w-8">
					<X size={17} strokeWidth={1.8} aria-hidden="true" />
				</button>
			</div>

			<form class="px-5 py-4" onsubmit={(e) => { e.preventDefault(); void saveEdit(); }}>
				<div class="grid grid-cols-2 gap-3">
					<label class={label}>
						Display name
						<input type="text" bind:value={eDisplay} class={field} />
					</label>
					<label class={label}>
						Category
						<select bind:value={eCategory} class={field}>
							{#each CATEGORIES as c (c)}
								<option value={c}>{c}</option>
							{/each}
						</select>
					</label>
					<label class={label}>
						Contract size
						<input type="number" bind:value={eContract} min="0" step="any" class={field} />
					</label>
					<label class={label}>
						Pip size
						<input type="number" bind:value={ePip} min="0" step="any" class={field} />
					</label>
					<label class={label}>
						Quote currency
						<input type="text" bind:value={eQuote} placeholder="USD" class={field} />
					</label>
					<label class="flex items-end gap-2 pb-1">
						<input type="checkbox" bind:checked={eEnabled} class="accent-accent" />
						<span class="text-[13px] text-fg">Enabled</span>
					</label>
				</div>

				{#if editError}
					<p role="alert" class="mt-3 rounded-xl border border-loss/40 bg-loss/8 px-3 py-2 text-[13px] text-loss">
						{editError}
					</p>
				{/if}

				<div class="mt-4 flex items-center justify-end gap-2 border-t border-line pt-4">
					<button type="button" onclick={() => cancelEdit()} disabled={editSaving} class="btn h-9 px-4 text-[13px]">
						Cancel
					</button>
					<button type="submit" disabled={editSaving} class="btn btn-primary h-9 px-4 text-[13px]">
						{editSaving ? 'Saving…' : 'Save'}
					</button>
				</div>
			</form>
		</div>
	</div>
{/if}
