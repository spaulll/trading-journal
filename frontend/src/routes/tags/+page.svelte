<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { GitMerge, Pencil, X } from 'lucide-svelte';
	import { fade, scale } from 'svelte/transition';
	import PageHead from '$lib/components/PageHead.svelte';
	import SegControl from '$lib/components/SegControl.svelte';
	import StateBlock from '$lib/components/StateBlock.svelte';
	import { api, errMsg, type TagSummaryDto } from '$lib/api';
	import { drillIntoTag } from '$lib/stores/ledger';
	import { toasts } from '$lib/stores/toast';
	import { fmtDate, fmtMoney, pnlTone, toneText } from '$lib/utils/format';
	import { FADE, MODAL } from '$lib/utils/transitions';

	type Scope = 'all' | 'setup' | 'mistake';

	let tags = $state<TagSummaryDto[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let scope = $state<Scope>('all');

	let modal = $state<null | { tag: TagSummaryDto }>(null);
	let fName = $state('');
	let fCategory = $state<'setup' | 'mistake'>('setup');
	let fMerge = $state('');
	let saving = $state(false);
	let formError = $state<string | null>(null);

	onMount(() => {
		void load();
	});

	async function load(): Promise<void> {
		loading = true;
		error = null;
		try {
			tags = await api.listTags();
		} catch (e) {
			error = errMsg(e);
		} finally {
			loading = false;
		}
	}

	const shown = $derived(tags.filter((t) => scope === 'all' || t.category === scope));
	const setups = $derived(tags.filter((t) => t.category === 'setup').length);
	const mistakes = $derived(tags.filter((t) => t.category === 'mistake').length);
	const others = $derived(modal ? tags.filter((t) => t.id !== modal?.tag.id) : []);

	function openEdit(tag: TagSummaryDto): void {
		fName = tag.name;
		fCategory = tag.category === 'mistake' ? 'mistake' : 'setup';
		fMerge = '';
		formError = null;
		modal = { tag };
	}

	/** Open the ledger on this tag — the same drill-down the performance bar does. */
	function drill(name: string): void {
		drillIntoTag(name);
		void goto('/');
	}

	async function save(): Promise<void> {
		if (!modal) return;
		const name = fName.trim().toLowerCase();
		if (!name) {
			formError = 'Name must not be empty.';
			return;
		}
		saving = true;
		formError = null;
		try {
			await api.patchTag(modal.tag.id, { name, category: fCategory });
			tags = await api.listTags();
			modal = null;
			toasts.push('success', `Tag #${name} saved.`);
		} catch (e) {
			formError = errMsg(e);
		} finally {
			saving = false;
		}
	}

	async function merge(): Promise<void> {
		if (!modal || !fMerge) return;
		saving = true;
		formError = null;
		try {
			const r = await api.mergeTags(modal.tag.id, Number(fMerge));
			tags = await api.listTags();
			modal = null;
			toasts.push('success', `Merged #${r.merged} into #${r.into} — ${r.trades} trades moved.`);
		} catch (e) {
			formError = errMsg(e);
		} finally {
			saving = false;
		}
	}

	const field = 'field font-mono text-[13px]';
	const label = 'flex flex-col gap-1.5 text-[11px] font-medium tracking-[0.14em] uppercase text-dim';
	const cols = 'grid grid-cols-[minmax(140px,1.6fr)_90px_110px_100px_130px_56px] gap-3 px-3 py-2.5';
</script>

<svelte:head>
	<title>Tags · Trading Journal</title>
</svelte:head>

<PageHead eyebrow="workspace" title="Tags" meta="{tags.length} tags · {setups} setups · {mistakes} mistakes" />

{#if loading}
	<div class="grid grid-cols-1 gap-3 md:grid-cols-2">
		{#each Array(6) as _}
			<div class="skeleton h-20"></div>
		{/each}
	</div>
{:else if error}
	<StateBlock
		kind="error"
		title="Couldn't reach the backend"
		body="{error} — start the API and retry."
		actionLabel="Retry"
		onAction={() => void load()}
	/>
{:else if tags.length === 0}
	<StateBlock
		title="No tags yet"
		body="Tag a trade with #setup or !mistake and the taxonomy builds itself from the ledger."
	/>
{:else}
	<div class="mb-3">
		<SegControl
			mode="tabs"
			label="Tag taxonomy"
			value={scope}
			onChange={(v) => (scope = v as Scope)}
			size="sm"
			options={[
				{ value: 'all', label: 'All', count: tags.length },
				{ value: 'setup', label: 'Setups', count: setups },
				{ value: 'mistake', label: 'Mistakes', count: mistakes }
			]}
		/>
	</div>

	<!-- Desktop: one dense row per tag. -->
	<div class="card hidden overflow-x-auto md:block">
		<div class="min-w-[760px]">
			<div class="border-b border-line bg-raised/40 {cols}">
				<span class="thead">Tag</span>
				<span class="thead text-right">Trades</span>
				<span class="thead text-right">Net</span>
				<span class="thead text-right">Win rate</span>
				<span class="thead">Last used</span>
				<span class="thead text-right">Edit</span>
			</div>
			{#each shown as t (t.id)}
				<div class="row-line {cols} items-center border-b border-line/50 last:border-b-0">
					<span class="flex min-w-0 items-center gap-2">
						<button
							type="button"
							onclick={() => drill(t.name)}
							title="Open the ledger on #{t.name}"
							class="num truncate text-[13px] font-semibold text-fg underline decoration-line/60 underline-offset-2 transition-colors hover:decoration-accent"
						>
							{t.category === 'mistake' ? '!' : '#'}{t.name}
						</button>
						<span class="rounded-md px-1.5 py-0.5 font-mono text-[10px] font-bold tracking-[0.1em] uppercase {t.category === 'mistake' ? 'tag-mistake' : 'tag-setup'}">
							{t.category}
						</span>
					</span>
					<span class="num text-right text-[12.5px] tabular-nums text-mut">{t.trade_count}</span>
					<span class="num text-right text-[12.5px] font-semibold tabular-nums {toneText[pnlTone(t.net_pnl)]}">
						{fmtMoney(t.net_pnl)}
					</span>
					<span class="num text-right text-[12.5px] tabular-nums text-mut">
						{t.win_rate === null ? '—' : `${t.win_rate.toFixed(1)}%`}
					</span>
					<span class="num text-[12px] text-dim">{fmtDate(t.last_used)}</span>
					<span class="flex justify-end">
						<button type="button" onclick={() => openEdit(t)} aria-label="Edit #{t.name}" class="btn-icon h-8 w-8">
							<Pencil size={15} strokeWidth={1.8} aria-hidden="true" />
						</button>
					</span>
				</div>
			{/each}
		</div>
	</div>

	<!-- Mobile: one card per tag. -->
	<div class="grid grid-cols-1 gap-2.5 md:hidden">
		{#each shown as t (t.id)}
			<article class="card p-3.5" aria-label="Tag #{t.name}">
				<div class="flex items-center justify-between gap-2">
					<span class="flex min-w-0 items-center gap-2">
						<button
							type="button"
							onclick={() => drill(t.name)}
							title="Open the ledger on #{t.name}"
							class="num truncate text-sm font-semibold text-fg underline decoration-line/60 underline-offset-2 transition-colors hover:decoration-accent"
						>
							{t.category === 'mistake' ? '!' : '#'}{t.name}
						</button>
						<span class="rounded-md px-1.5 py-0.5 font-mono text-[10px] font-bold tracking-[0.1em] uppercase {t.category === 'mistake' ? 'tag-mistake' : 'tag-setup'}">
							{t.category}
						</span>
					</span>
					<button type="button" onclick={() => openEdit(t)} aria-label="Edit #{t.name}" class="btn-icon h-8 w-8">
						<Pencil size={15} strokeWidth={1.8} aria-hidden="true" />
					</button>
				</div>
				<p class="num mt-2 text-[12px] text-dim">
					{t.trade_count} trades · <span class="font-semibold {toneText[pnlTone(t.net_pnl)]}">{fmtMoney(t.net_pnl)}</span>
					· {t.win_rate === null ? 'no decided trades' : `${t.win_rate.toFixed(1)}% win rate`}
					· {fmtDate(t.last_used)}
				</p>
			</article>
		{/each}
	</div>
{/if}

{#if modal}
	<div
		transition:fade={FADE}
		onclick={(e) => e.target === e.currentTarget && (modal = null)}
		onkeydown={(e) => e.key === 'Escape' && (modal = null)}
		tabindex={-1}
		class="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-base/75 p-4 backdrop-blur-[3px]"
		role="dialog"
		aria-modal="true"
		aria-label="Edit tag"
	>
		<div transition:scale={MODAL} class="card w-full max-w-md overflow-hidden p-0 shadow-pop">
			<div class="flex items-center gap-2.5 border-b border-line px-5 py-4">
				<h2 class="display text-xl text-fg">#{modal.tag.name}</h2>
				<button type="button" onclick={() => (modal = null)} aria-label="Close" class="btn-icon ml-auto h-8 w-8">
					<X size={17} strokeWidth={1.8} aria-hidden="true" />
				</button>
			</div>
			<form class="px-5 py-4" onsubmit={save}>
				<div class="grid grid-cols-2 gap-3">
					<label class={label}>Name<input type="text" bind:value={fName} class="{field} lowercase" /></label>
					<label class={label}>Taxonomy
						<select bind:value={fCategory} class={field}>
							<option value="setup">setup</option>
							<option value="mistake">mistake</option>
						</select>
					</label>
				</div>
				{#if formError}
					<p role="alert" class="mt-3 text-[12.5px] text-loss">{formError}</p>
				{/if}
				<div class="mt-4 flex items-center justify-end gap-2">
					<button type="button" onclick={() => (modal = null)} class="btn btn-ghost h-9 px-3 text-[13px]">Cancel</button>
					<button type="submit" disabled={saving} class="btn btn-primary h-9 px-3 text-[13px] disabled:opacity-50">
						{saving ? 'Saving…' : 'Save'}
					</button>
				</div>
			</form>

			<div class="border-t border-line px-5 py-4">
				<p class="eyebrow">Merge into another tag</p>
				<p class="mt-1 text-[12px] text-dim">
					The trades that carried this tag carry the target instead, and this name disappears.
				</p>
				<div class="mt-2.5 flex items-center gap-2">
					<select bind:value={fMerge} class="{field} flex-1" aria-label="Merge into">
						<option value="">Pick a tag…</option>
						{#each others as t (t.id)}
							<option value={String(t.id)}>{t.category === 'mistake' ? '!' : '#'}{t.name}</option>
						{/each}
					</select>
					<button
						type="button"
						onclick={() => void merge()}
						disabled={!fMerge || saving}
						class="btn btn-ghost h-9 shrink-0 gap-1.5 px-3 text-[13px] disabled:opacity-40"
					>
						<GitMerge size={14} strokeWidth={2} aria-hidden="true" />
						Merge
					</button>
				</div>
			</div>
		</div>
	</div>
{/if}
