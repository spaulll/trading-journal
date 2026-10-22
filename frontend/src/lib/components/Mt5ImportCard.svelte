<script lang="ts">
	import { onMount } from 'svelte';
	import { FileUp, History, Upload } from 'lucide-svelte';
	import { api, errMsg, type ImportDetailDto, type ImportRunDto, type Mt5ImportResult } from '$lib/api';
	import { accounts, loadAccounts } from '$lib/stores/accounts';
	import { toasts } from '$lib/stores/toast';
	import { fmtDateTime } from '$lib/utils/format';

	let file = $state<File | null>(null);
	let accountId = $state('');
	let busy = $state(false);
	let result = $state<Mt5ImportResult | null>(null);
	let error = $state<string | null>(null);
	let input = $state<HTMLInputElement | undefined>();
	let runs = $state<ImportRunDto[]>([]);
	let runsError = $state<string | null>(null);

	onMount(() => {
		if ($accounts.length === 0) void loadAccounts();
		void loadRuns();
	});

	async function loadRuns(): Promise<void> {
		try {
			const res = await api.importRuns(8);
			runs = res.runs;
			runsError = null;
		} catch (e) {
			runsError = errMsg(e);
		}
	}

	function pick(event: Event): void {
		const files = (event.currentTarget as HTMLInputElement).files;
		file = files && files.length > 0 ? files[0] : null;
		result = null;
		error = null;
	}

	async function run(): Promise<void> {
		if (!file || busy) return;
		busy = true;
		error = null;
		try {
			const res = await api.importStatement(file, accountId ? Number(accountId) : null);
			result = res;
			const { added, updated, unchanged, skipped } = res.counts;
			toasts.push(
				added + updated > 0 ? 'success' : 'info',
				`Statement read: ${added} added, ${updated} updated, ${unchanged} unchanged, ${skipped} skipped.`
			);
			// The same file can be picked again to confirm it changes nothing.
			if (input) input.value = '';
			file = null;
		} catch (e) {
			error = errMsg(e);
		} finally {
			busy = false;
			void loadRuns();
		}
	}

	const known = $derived(
		result ? [...result.added, ...result.updated, ...result.unchanged, ...result.skipped] : []
	);
	const updatedDetails = $derived(
		result ? result.details.filter((d) => d.action === 'updated') : []
	);

	function shown(value: unknown): string {
		if (value === null || value === undefined) return '—';
		if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(4);
		const text = String(value);
		return text.length > 16 ? `${text.slice(0, 16)}…` : text;
	}

	/** `size 0.1 → 0.2 · fees 1 → 2` — what the statement changed on a ticket. */
	function changeSummary(detail: ImportDetailDto): string {
		return Object.entries(detail.changes ?? {})
			.map(([key, change]) => `${key} ${shown(change.from)} → ${shown(change.to)}`)
			.join(' · ');
	}

	function runSummary(run: ImportRunDto): string {
		return `${run.added} added · ${run.updated} updated · ${run.unchanged} unchanged · ${run.skipped} skipped`;
	}

	function shortName(name: string): string {
		return name.length > 42 ? `${name.slice(0, 41)}…` : name;
	}
</script>

<section aria-label="MT5 statement import" class="card rise mb-4 p-5">
	<div class="flex flex-wrap items-center gap-2">
		<FileUp size={16} strokeWidth={2} aria-hidden="true" class="text-accent" />
		<h2 class="text-[15px] font-semibold text-fg">Broker import</h2>
		<span class="num text-[12px] text-dim">MT5 statement · HTML report or CSV export</span>
	</div>

	<div class="mt-3 flex flex-col gap-2 sm:flex-row sm:items-end">
		<label class="flex min-w-0 flex-1 flex-col gap-1">
			<span class="font-mono text-[10px] tracking-[0.14em] text-dim uppercase">Statement</span>
			<input
				bind:this={input}
				type="file"
				accept=".htm,.html,.csv,.txt"
				onchange={pick}
				aria-label="MT5 statement file"
				class="field h-9 w-full px-2 text-[12px] file:mr-2 file:rounded-md file:border-0 file:bg-raised file:px-2 file:py-1 file:font-mono file:text-[11px] file:text-fg"
			/>
		</label>
		<label class="flex w-full flex-col gap-1 sm:w-52">
			<span class="font-mono text-[10px] tracking-[0.14em] text-dim uppercase">Account</span>
			<select bind:value={accountId} class="field h-9 px-2 text-[12px]" aria-label="Import account">
				<option value="">From the statement</option>
				{#each $accounts as a (a.id)}
					<option value={String(a.id)}>@{a.alias}</option>
				{/each}
			</select>
		</label>
		<button
			type="button"
			onclick={() => void run()}
			disabled={!file || busy}
			class="btn btn-primary h-9 shrink-0 px-4 text-[13px] disabled:opacity-50"
		>
			<Upload size={14} strokeWidth={2.2} aria-hidden="true" />
			{busy ? 'Importing…' : 'Import'}
		</button>
	</div>

	{#if busy}
		<div class="skeleton card mt-3 h-16" aria-hidden="true"></div>
	{:else if error}
		<p role="alert" class="mt-3 rounded-xl border border-loss/40 bg-loss/8 px-3 py-2 text-[13px] text-loss">
			Import failed — {error}
		</p>
	{:else if result}
		<div class="mt-3 rounded-xl border border-line bg-raised/30 px-4 py-3" aria-label="Import result">
			<div class="flex flex-wrap items-baseline gap-x-3 gap-y-1">
				<span class="num text-[13px] font-semibold text-fg">
					{result.counts.added} added · {result.counts.updated} updated · {result.counts.unchanged} unchanged ·
					{result.counts.skipped} skipped
				</span>
				<span class="num text-[11px] text-dim">
					{result.counts.rows} rows · {result.format.toUpperCase()} · {result.filename}
				</span>
			</div>
			{#if result.account_id === null}
				<p class="num mt-1 text-[11px] text-dim">
					No account matched{result.account_login ? ` login ${result.account_login}` : ''} — rows stay unassigned.
				</p>
			{/if}
			{#if result.warnings.length > 0}
				<ul class="mt-2 flex flex-col gap-0.5">
					{#each result.warnings as warning}
						<li class="text-[12px] text-accent">{warning}</li>
					{/each}
				</ul>
			{/if}
			{#if updatedDetails.length > 0}
				<ul class="mt-2 flex flex-col gap-0.5">
					{#each updatedDetails.slice(0, 5) as detail (detail.ticket)}
						<li class="num truncate text-[11px] text-mut" title={changeSummary(detail)}>
							<span class="text-fg">{detail.ticket}</span> · {changeSummary(detail)}
						</li>
					{/each}
					{#if updatedDetails.length > 5}
						<li class="num text-[11px] text-dim">+{updatedDetails.length - 5} more updated</li>
					{/if}
				</ul>
			{/if}
			{#if known.length > 0}
				<p class="num mt-2 truncate text-[11px] text-dim" title={known.join(', ')}>
					{known.slice(0, 12).join(' · ')}{known.length > 12 ? ` · +${known.length - 12} more` : ''}
				</p>
			{/if}
		</div>
	{/if}

	{#if runs.length > 0 || runsError}
		<div class="mt-4 border-t border-line/70 pt-3" aria-label="Import history">
			<div class="flex items-center gap-2">
				<History size={13} strokeWidth={2} aria-hidden="true" class="text-dim" />
				<h3 class="font-mono text-[10px] tracking-[0.14em] text-dim uppercase">Recent imports</h3>
			</div>
			{#if runsError}
				<p class="mt-1 text-[11px] text-loss">History unavailable — {runsError}</p>
			{:else}
				<ul class="mt-1">
					{#each runs.slice(0, 5) as run (run.id)}
						<li class="border-b border-line/60 py-1.5 last:border-0">
							<div class="flex min-w-0 items-baseline gap-2">
								<span class="num min-w-0 flex-1 break-all text-[11px] text-fg" title={run.filename}>
									{shortName(run.filename)}
								</span>
								<span class="num shrink-0 text-[10px] text-dim">{run.format?.toUpperCase() ?? 'FAILED'}</span>
							</div>
							<div class="mt-0.5 flex min-w-0 flex-col gap-0.5 sm:flex-row sm:flex-wrap sm:items-baseline sm:gap-x-2">
								{#if run.error}
									<span class="min-w-0 flex-1 break-words text-[11px] text-loss">{run.error}</span>
								{:else}
									<span class="num min-w-0 flex-1 text-[11px] text-mut">{runSummary(run)}</span>
								{/if}
								<span class="num shrink-0 text-[10px] text-dim sm:ml-auto">{fmtDateTime(run.created_at)}</span>
							</div>
						</li>
					{/each}
				</ul>
			{/if}
		</div>
	{/if}
</section>
