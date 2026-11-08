<script lang="ts">
	import { BookOpen, Plus, Save, X } from 'lucide-svelte';
	import { api, errMsg, type SymbolSpecDto } from '$lib/api';
	import { toasts } from '$lib/stores/toast';
	import { fmtNum } from '$lib/utils/format';

	let specs = $state<SymbolSpecDto[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	// Add form
	let adding = $state(false);
	let saving = $state(false);
	let fSymbol = $state('');
	let fDisplay = $state('');
	let fCategory = $state('fx');
	let fContract = $state('100000');
	let fPip = $state('0.01');
	let fQuote = $state('USD');
	let fEnabled = $state(true);
	let formError = $state<string | null>(null);

	const CATEGORIES = ['fx', 'metal', 'crypto', 'index', 'future'];

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
			formError = 'Symbol is required.';
			return;
		}
		if (!Number.isFinite(contract) || contract <= 0) {
			formError = 'Contract size must be a positive number.';
			return;
		}
		if (!Number.isFinite(pip) || pip <= 0) {
			formError = 'Pip size must be a positive number.';
			return;
		}
		saving = true;
		formError = null;
		try {
			await api.createSymbol({
				symbol,
				display: fDisplay.trim() || symbol,
				category: fCategory,
				contract_size: contract,
				pip_size: pip,
				quote_currency: fQuote.trim().toUpperCase() || 'USD',
				enabled: fEnabled
			});
			toasts.push('success', `${symbol} registered — future trades on it will be priced.`);
			adding = false;
			fSymbol = '';
			fDisplay = '';
			fCategory = 'fx';
			fContract = '100000';
			fPip = '0.01';
			fQuote = 'USD';
			fEnabled = true;
			await load();
		} catch (e) {
			formError = errMsg(e);
		} finally {
			saving = false;
		}
	}

	// Inline edit
	let editingId = $state<number | null>(null);
	let eContract = $state('');
	let ePip = $state('');
	let eQuote = $state('');
	let eDisplay = $state('');
	let eCategory = $state('');
	let eEnabled = $state(true);
	let editSaving = $state(false);
	let editError = $state<string | null>(null);

	function beginEdit(spec: SymbolSpecDto): void {
		editingId = spec.id;
		eContract = String(spec.contract_size);
		ePip = String(spec.pip_size);
		eQuote = spec.quote_currency;
		eDisplay = spec.display;
		eCategory = spec.category;
		eEnabled = spec.enabled;
		editError = null;
	}

	function cancelEdit(): void {
		editingId = null;
		editError = null;
	}

	async function saveEdit(spec: SymbolSpecDto): Promise<void> {
		const contract = Number(eContract);
		const pip = Number(ePip);
		if (!Number.isFinite(contract) || contract <= 0) {
			editError = 'Contract size must be a positive number.';
			return;
		}
		if (!Number.isFinite(pip) || pip <= 0) {
			editError = 'Pip size must be a positive number.';
			return;
		}
		editSaving = true;
		editError = null;
		try {
			await api.updateSymbol(spec.id, {
				display: eDisplay.trim() || spec.symbol,
				category: eCategory,
				contract_size: contract,
				pip_size: pip,
				quote_currency: eQuote.trim().toUpperCase() || 'USD',
				enabled: eEnabled
			});
			toasts.push('success', `${spec.symbol} updated.`);
			editingId = null;
			await load();
		} catch (e) {
			editError = errMsg(e);
		} finally {
			editSaving = false;
		}
	}

	function catTone(category: string): string {
		switch (category) {
			case 'fx':
				return 'text-accent';
			case 'metal':
				return 'text-win';
			case 'crypto':
				return 'text-loss';
			case 'index':
				return 'text-flat';
			default:
				return 'text-dim';
		}
	}
</script>

<section aria-label="Symbol contracts" class="card rise flex h-full flex-col p-4">
	<div class="flex flex-wrap items-center gap-x-2 gap-y-1">
		<BookOpen size={16} strokeWidth={2} aria-hidden="true" class="text-accent" />
		<h2 class="text-[15px] font-semibold text-fg">Symbol contracts</h2>
		<span class="num text-[11px] text-dim">Registry · contract sizes &amp; quote currencies</span>
	</div>

	<p class="mt-1.5 text-[12px] leading-snug text-mut">
		Every registered symbol gets a real dollar P&amp;L. Contracts differ per firm — add or adjust any pair here.
	</p>

	<div class="mt-3 flex flex-wrap items-center gap-2">
		{#if !adding}
			<button type="button" onclick={beginAdd} class="btn h-9 px-4 text-[13px]">
				<Plus size={14} aria-hidden="true" class="mr-1" /> Add symbol
			</button>
		{/if}
		{#if error}
			<span class="num text-[11px] text-loss">Could not load registry — {error}</span>
		{/if}
	</div>

	{#if adding}
		<div class="mt-3 rounded-xl border border-line bg-raised/30 p-3" aria-label="Add symbol form">
			<p class="eyebrow">Register a new pair</p>
			<div class="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3">
				<label class="flex min-w-0 flex-col gap-1">
					<span class="eyebrow">Symbol</span>
					<input type="text" bind:value={fSymbol} placeholder="EURTRY" class="field h-9 font-mono text-[13px]" />
				</label>
				<label class="flex min-w-0 flex-col gap-1">
					<span class="eyebrow">Display name</span>
					<input type="text" bind:value={fDisplay} placeholder="EUR/TRY" class="field h-9 text-[13px]" />
				</label>
				<label class="flex min-w-0 flex-col gap-1">
					<span class="eyebrow">Category</span>
					<select bind:value={fCategory} class="field h-9 text-[13px]">
						{#each CATEGORIES as c (c)}
							<option value={c}>{c}</option>
						{/each}
					</select>
				</label>
				<label class="flex min-w-0 flex-col gap-1">
					<span class="eyebrow">Contract size</span>
					<input type="number" bind:value={fContract} class="field h-9 font-mono text-[13px]" />
				</label>
				<label class="flex min-w-0 flex-col gap-1">
					<span class="eyebrow">Pip size</span>
					<input type="number" bind:value={fPip} step="any" class="field h-9 font-mono text-[13px]" />
				</label>
				<label class="flex min-w-0 flex-col gap-1">
					<span class="eyebrow">Quote currency</span>
					<input type="text" bind:value={fQuote} placeholder="USD" class="field h-9 font-mono text-[13px]" />
				</label>
			</div>
			<div class="mt-2 flex flex-wrap items-center gap-2">
				<label class="inline-flex items-center gap-1.5 text-[12px] text-dim">
					<input type="checkbox" bind:checked={fEnabled} class="accent-accent" />
					Enabled
				</label>
				<button type="button" onclick={() => void create()} disabled={saving} class="btn btn-primary h-8 px-3 text-[13px]">
					{saving ? 'Saving…' : 'Register'}
				</button>
				<button type="button" onclick={cancelAdd} disabled={saving} class="btn h-8 px-3 text-[13px]">
					Cancel
				</button>
				{#if formError}
					<span role="alert" class="num text-[11px] text-loss">{formError}</span>
				{/if}
			</div>
		</div>
	{/if}

	<div class="mt-3 overflow-x-auto">
		<table class="w-full text-left text-[12px]">
			<thead>
				<tr class="eyebrow text-[10px] uppercase tracking-wide">
					<th class="py-1 pr-2">Symbol</th>
					<th class="py-1 pr-2">Quote</th>
					<th class="py-1 pr-2 text-right">Contract</th>
					<th class="py-1 pr-2 text-right">Pip</th>
					<th class="py-1 pr-2">Category</th>
					<th class="py-1 pr-2">State</th>
					<th class="py-1 text-right">Edit</th>
				</tr>
			</thead>
			<tbody>
				{#each specs as spec (spec.id)}
					{#if editingId === spec.id}
						<tr class="border-t border-line">
							<td colspan="6" class="py-2">
								<div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
									<label class="flex min-w-0 flex-col gap-0.5">
										<span class="eyebrow">Display</span>
										<input type="text" bind:value={eDisplay} class="field h-8 text-[12px]" />
									</label>
									<label class="flex min-w-0 flex-col gap-0.5">
										<span class="eyebrow">Contract size</span>
										<input type="number" bind:value={eContract} class="field h-8 font-mono text-[12px]" />
									</label>
									<label class="flex min-w-0 flex-col gap-0.5">
										<span class="eyebrow">Pip size</span>
										<input type="number" bind:value={ePip} step="any" class="field h-8 font-mono text-[12px]" />
									</label>
									<label class="flex min-w-0 flex-col gap-0.5">
										<span class="eyebrow">Quote currency</span>
										<input type="text" bind:value={eQuote} class="field h-8 font-mono text-[12px]" />
									</label>
									<label class="flex min-w-0 flex-col gap-0.5">
										<span class="eyebrow">Category</span>
										<select bind:value={eCategory} class="field h-8 text-[12px]">
											{#each CATEGORIES as c (c)}
												<option value={c}>{c}</option>
											{/each}
										</select>
									</label>
									<label class="flex min-w-0 items-center gap-1.5 text-[12px] text-dim">
										<input type="checkbox" bind:checked={eEnabled} class="accent-accent" />
										Enabled
									</label>
								</div>
								<div class="mt-2 flex flex-wrap items-center gap-2">
									<button type="button" onclick={() => void saveEdit(spec)} disabled={editSaving} class="btn btn-primary h-8 px-3 text-[12px]">
										<Save size={13} aria-hidden="true" class="mr-1" /> {editSaving ? 'Saving…' : 'Save'}
									</button>
									<button type="button" onclick={cancelEdit} disabled={editSaving} class="btn h-8 px-3 text-[12px]">
										<X size={13} aria-hidden="true" class="mr-1" /> Cancel
									</button>
									{#if editError}
										<span role="alert" class="num text-[11px] text-loss">{editError}</span>
									{/if}
								</div>
							</td>
						</tr>
					{:else}
						<tr class="border-t border-line">
							<td class="py-1.5 pr-2">
								<span class="num font-semibold text-fg">{spec.symbol}</span>
								<span class="block text-[10px] text-dim">{spec.display}</span>
							</td>
							<td class="py-1.5 pr-2"><span class="num text-mut">{spec.quote_currency}</span></td>
							<td class="py-1.5 pr-2 text-right"><span class="num text-mut">{fmtNum(spec.contract_size)}</span></td>
							<td class="py-1.5 pr-2 text-right"><span class="num text-mut">{fmtNum(spec.pip_size)}</span></td>
							<td class="py-1.5 pr-2"><span class="text-[10px] uppercase tracking-wide {catTone(spec.category)}">{spec.category}</span></td>
							<td class="py-1.5 pr-2">
								<span class="num text-[10px] uppercase tracking-wide {spec.enabled ? 'text-win' : 'text-dim'}">
									{spec.enabled ? 'on' : 'off'}
								</span>
							</td>
							<td class="py-1.5 text-right">
								<button type="button" onclick={() => beginEdit(spec)} class="btn h-7 px-2 text-[11px]">
									Edit
								</button>
							</td>
						</tr>
					{/if}
				{/each}
				{#if !loading && specs.length === 0}
					<tr class="border-t border-line">
						<td colspan="7" class="py-3 text-center text-[12px] text-dim">No symbols registered — add one above.</td>
					</tr>
				{/if}
			</tbody>
		</table>
		{#if loading}
			<p class="mt-2 text-[11px] text-dim">Loading registry…</p>
		{/if}
	</div>
</section>
