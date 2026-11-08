<script lang="ts">
	import { BookOpen, Plus, Save, X } from 'lucide-svelte';
	import { api, errMsg, type SymbolSpecDto } from '$lib/api';
	import { toasts } from '$lib/stores/toast';
	import { fmtNum } from '$lib/utils/format';

	let specs = $state<SymbolSpecDto[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

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

	// Inline edit (same row, tiny inputs)
	let editingId = $state<number | null>(null);
	let eContract = $state('');
	let ePip = $state('');
	let eQuote = $state('');
	let eEnabled = $state(true);
	let editSaving = $state(false);
	let editError = $state<string | null>(null);

	function beginEdit(spec: SymbolSpecDto): void {
		editingId = spec.id;
		eContract = String(spec.contract_size);
		ePip = String(spec.pip_size);
		eQuote = spec.quote_currency;
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
			await api.updateSymbol(spec.id, {
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
		<span class="num text-[11px] text-dim">{specs.length} registered</span>
	</div>

	<p class="mt-1 text-[12px] leading-snug text-mut">
		Contracts differ per firm — add or adjust any pair here.
	</p>

	{#if adding}
		<div class="mt-2.5 rounded-xl border border-line bg-raised/30 px-3 py-2.5" aria-label="Add symbol form">
			<div class="flex flex-wrap items-center gap-2">
				<label class="flex min-w-0 items-center gap-1.5">
					<span class="eyebrow">Symbol</span>
					<input type="text" bind:value={fSymbol} placeholder="EURTRY" class="field h-8 w-20 font-mono text-[12px]" />
				</label>
				<label class="flex items-center gap-1.5">
					<span class="eyebrow">Contract</span>
					<input type="number" bind:value={fContract} class="field h-8 w-20 font-mono text-[12px]" />
				</label>
				<label class="flex items-center gap-1.5">
					<span class="eyebrow">Pip</span>
					<input type="number" bind:value={fPip} step="any" class="field h-8 w-16 font-mono text-[12px]" />
				</label>
				<label class="flex items-center gap-1.5">
					<span class="eyebrow">Quote</span>
					<input type="text" bind:value={fQuote} placeholder="USD" class="field h-8 w-14 font-mono text-[12px]" />
				</label>
				<label class="flex items-center gap-1.5">
					<span class="eyebrow">Type</span>
					<select bind:value={fCategory} class="field h-8 text-[12px]">
						{#each CATEGORIES as c (c)}
							<option value={c}>{c}</option>
						{/each}
					</select>
				</label>
				<div class="ml-auto flex items-center gap-1.5">
					<button type="button" onclick={() => void create()} disabled={saving} class="btn btn-primary h-8 px-3 text-[12px]">
						{saving ? 'Saving…' : 'Register'}
					</button>
					<button type="button" onclick={cancelAdd} disabled={saving} class="btn h-8 px-2.5 text-[12px]">
						<X size={13} aria-hidden="true" />
					</button>
				</div>
			</div>
			{#if formError}
				<p role="alert" class="num mt-1.5 text-[11px] text-loss">{formError}</p>
			{/if}
		</div>
	{:else}
		<div class="mt-2.5">
			<button type="button" onclick={beginAdd} class="btn h-8 px-3 text-[12px]">
				<Plus size={13} aria-hidden="true" class="mr-1" /> Add symbol
			</button>
			{#if error}
				<span class="num ml-2 text-[11px] text-loss">{error}</span>
			{/if}
		</div>
	{/if}

	<div class="mt-2.5 min-h-0 flex-1 overflow-y-auto rounded-xl border border-line">
		<table class="w-full border-collapse text-left text-[12px]">
			<thead>
				<tr class="eyebrow sticky top-0 bg-raised text-[10px] uppercase tracking-wide">
					<th class="py-1.5 pl-3 pr-2">Symbol</th>
					<th class="py-1.5 pr-2 text-right">Contract</th>
					<th class="py-1.5 pr-2 text-right">Pip</th>
					<th class="py-1.5 pr-2">Quote</th>
					<th class="py-1.5 pr-2">Type</th>
					<th class="py-1.5 pr-3 text-right">Edit</th>
				</tr>
			</thead>
			<tbody>
				{#each specs as spec (spec.id)}
					{#if editingId === spec.id}
						<tr class="border-t border-line bg-raised/30">
							<td class="py-1 pl-3 pr-2">
								<span class="num text-[12px] font-semibold text-fg">{spec.symbol}</span>
							</td>
							<td class="py-1 pr-2">
								<input type="number" bind:value={eContract} class="field h-7 w-20 font-mono text-[11px]" />
							</td>
							<td class="py-1 pr-2">
								<input type="number" bind:value={ePip} step="any" class="field h-7 w-16 font-mono text-[11px]" />
							</td>
							<td class="py-1 pr-2">
								<input type="text" bind:value={eQuote} class="field h-7 w-12 font-mono text-[11px]" />
							</td>
							<td class="py-1 pr-2">
								<label class="inline-flex items-center gap-1" title="Enabled">
									<input type="checkbox" bind:checked={eEnabled} class="accent-accent" />
								</label>
							</td>
							<td class="py-1 pl-2 pr-3 text-right">
								<div class="inline-flex items-center gap-1">
									<button type="button" onclick={() => void saveEdit(spec)} disabled={editSaving} class="btn btn-primary h-7 px-2 text-[11px]">
										<Save size={12} aria-hidden="true" class="mr-0.5" /> {editSaving ? '…' : 'Save'}
									</button>
									<button type="button" onclick={cancelEdit} disabled={editSaving} class="btn h-7 px-2 text-[11px]">
										Cancel
									</button>
								</div>
								{#if editError}
									<span class="num block text-[10px] text-loss">{editError}</span>
								{/if}
							</td>
						</tr>
					{:else}
						<tr class="border-t border-line">
							<td class="py-1.5 pl-3 pr-2">
								<span class="num font-semibold text-fg">{spec.symbol}</span>
								<span class="text-[10px] uppercase tracking-wide text-dim {catTone(spec.category)}"> · {spec.category}</span>
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
								<button type="button" onclick={() => beginEdit(spec)} class="btn h-7 px-2 text-[11px]">
									Edit
								</button>
							</td>
						</tr>
					{/if}
				{/each}
				{#if !loading && specs.length === 0}
					<tr class="border-t border-line">
						<td colspan="6" class="py-3 text-center text-[12px] text-dim">No symbols registered yet.</td>
					</tr>
				{/if}
			</tbody>
		</table>
		{#if loading}
			<p class="p-3 text-[11px] text-dim">Loading registry…</p>
		{/if}
	</div>
</section>
