<script lang="ts">
	import { ChevronDown, Search } from 'lucide-svelte';
	import { slide } from 'svelte/transition';
	import { onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { api, type TradeDto } from '$lib/api';
	import { aliasOf, accounts, accountMap, chipAlias, loadAccounts, selectedAccountId } from '$lib/stores/accounts';
	import { gotoPage, ledgerFilters, ledgerQuery, pageCount, setLedgerAccount, setLedgerFilters, setPageSize, type LedgerSort, type LedgerStatus } from '$lib/stores/ledger';
	import { loadTrades, openTrade, requestClose, tradeCounts, trades, tradesPage, tradesPageSize, tradesTotal, upsertTrade } from '$lib/stores/trades';
	import { toasts } from '$lib/stores/toast';
	import { fmtCurrency, fmtDateTime, fmtMoney, fmtR, isUnpriced, pnlTone, rTone, toneBg, toneText, usdNet } from '$lib/utils/format';
	import SegControl from '$lib/components/SegControl.svelte';

	let moveTarget = $state('');
	let moving = $state(false);
	let moveOpen = $state(false);
	let selectMode = $state(false);
	let selected = $state<Set<number>>(new Set());
	let searchEl: HTMLInputElement | null = $state(null);
	let expanded = $state<Set<number>>(new Set());

	// The filters live in the shared store: the server does the matching, so
	// the browser only ever holds the rows it is showing. The text inputs
	// keep their own value so a keystroke does not fire a request per letter.
	let queryInput = $state('');
	let tagInput = $state('');

	onMount(() => {
		void loadAccounts();
		// The saved account scope is the ledger's starting filter; the shared
		// selection keeps it in step with the rest of the app.
		selectedAccountId.subscribe((v) => {
			setLedgerAccount(v === null ? '' : String(v));
		});
	});

	$effect(() => {
		const query = queryInput;
		const tag = tagInput;
		const timer = setTimeout(() => {
			const current = get(ledgerFilters);
			if (current.query === query && current.tag === tag) return;
			setLedgerFilters({ query, tag });
		}, 250);
		return () => clearTimeout(timer);
	});

	function onGlobalKey(e: KeyboardEvent): void {
		const target = e.target as HTMLElement | null;
		const typing =
			target &&
			(target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT');
		if (e.key === '/' && !typing) {
			e.preventDefault();
			searchEl?.focus();
		}
	}

	/** The broker-booked amount, for a tooltip beside its USD conversion. */
	function brokerLabel(t: TradeDto): string | undefined {
		const quote = (t.quote_currency ?? 'USD').toUpperCase();
		if (quote === 'USD' || t.net_pnl === null) return undefined;
		return `Broker booked ${fmtCurrency(t.net_pnl, quote)}`;
	}

	/** The rows the server sent — already filtered, sorted and counted there. */
	const filtered = $derived($trades);

	const counts = $derived($tradeCounts);

	/** The pager's own arithmetic — the server is the source of the total. */
	const pages = $derived(pageCount($tradesTotal, $tradesPageSize));
	const showingFrom = $derived($tradesTotal === 0 ? 0 : ($tradesPage - 1) * $tradesPageSize + 1);
	const showingTo = $derived(Math.min($tradesPage * $tradesPageSize, $tradesTotal));

	function toggleExpand(id: number, e: MouseEvent): void {
		e.stopPropagation();
		expanded = new Set(expanded.has(id) ? [...expanded].filter((x) => x !== id) : [...expanded, id]);
	}

	function tagChip(name: string, category: string): string {
		return `rounded-md px-1.5 py-0.5 font-mono text-[10.5px] ${
			category === 'mistake' ? 'tag-mistake' : 'tag-setup'
		}`;
	}

	async function moveFiltered(): Promise<void> {
		if (moving) return;
		moving = true;
		try {
			const target = moveTarget === 'unassigned' ? null : moveTarget ? Number(moveTarget) : null;
			if (moveTarget === '') return;
			// The ledger shows one page, so "move everything the filter
			// matches" is a question for the server, not for the rows on
			// screen.
			const ids = selectMode
				? filtered.filter((t) => selected.has(t.id)).map((t) => t.id)
				: (await api.listTradeIds(get(ledgerQuery))).ids;
			if (ids.length === 0) {
				toasts.push('success', 'Nothing to move — the filter matches no trades.');
				return;
			}
			const r = await api.bulkAccount(ids, target);
			await loadTrades(true);
			selected = new Set([...selected].filter((id) => !ids.includes(id)));
			toasts.push('success', `Moved ${r.updated} trade${r.updated === 1 ? '' : 's'} to ${moveTarget === 'unassigned' ? 'unassigned' : '@' + aliasOf(target)}.`);
		} catch (e) {
			toasts.push('error', `Move failed — ${e instanceof Error ? e.message : 'unknown error'}`);
		} finally {
			moving = false;
		}
	}

	function toggleSelectMode(): void {
		selectMode = !selectMode;
		if (!selectMode) selected = new Set();
	}

	function toggleOne(id: number): void {
		const next = new Set(selected);
		if (next.has(id)) next.delete(id);
		else next.add(id);
		selected = next;
	}

	function selectAllFiltered(): void {
		selected = new Set(filtered.map((t) => t.id));
	}

	function toggleAllFiltered(): void {
		if (allFilteredSelected) selected = new Set();
		else selected = new Set(filtered.map((t) => t.id));
	}

	function clearSelection(): void {
		selected = new Set();
	}

	const selectedVisibleCount = $derived(filtered.filter((t) => selected.has(t.id)).length);
	const allFilteredSelected = $derived(
		filtered.length > 0 && filtered.every((t) => selected.has(t.id))
	);

</script>

<svelte:window onkeydown={onGlobalKey} />

<section aria-label="Trade history" class="rise mt-9" style="animation-delay: 140ms">
	<div class="mb-3 flex flex-wrap items-center gap-2">
		<SegControl
			mode="tabs"
			label="Status filter"
			value={$ledgerFilters.status}
			onChange={(v) => setLedgerFilters({ status: v as LedgerStatus })}
			size="sm"
			options={[
				{ value: 'ALL', label: 'All', count: counts.ALL },
				{ value: 'OPEN', label: 'Open', count: counts.OPEN },
				{ value: 'CLOSED', label: 'Closed', count: counts.CLOSED }
			]}
		/>

		<label class="relative ml-auto flex-1 sm:max-w-56">
			<Search
				size={14}
				strokeWidth={1.8}
				aria-hidden="true"
				class="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-dim"
			/>
			<input
				type="search"
				bind:this={searchEl}
				bind:value={queryInput}
				placeholder="Symbol or ID…  ( / )"
				class="field h-9 pl-8 text-[13px]"
			/>
		</label>

		<label class="relative flex-1 sm:max-w-44">
			<span
				class="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 font-mono text-xs text-dim"
				aria-hidden="true">#</span>
			<input type="search" bind:value={tagInput} placeholder="Tag…" class="field h-9 pl-7 font-mono text-[13px]" />
		</label>

		<label
			class="relative flex h-9 items-center gap-1.5 rounded-xl border border-line bg-raised/70 px-2.5 text-sm text-dim"
		>
			<span class="font-mono text-[10px] tracking-[0.16em] uppercase">Acct</span>
			<select
				value={$ledgerFilters.account}
				onchange={(e) => setLedgerFilters({ account: e.currentTarget.value })}
				class="h-full max-w-32 appearance-none border-0 bg-none bg-transparent py-0 pr-6 text-[13px] text-fg outline-none [color-scheme:inherit] [&>option]:bg-panel [&>option]:text-fg"
				aria-label="Filter by account"
			>
				<option value="">All</option>
				<option value="unassigned">Unassigned</option>
				{#each $accounts as a (a.id)}
					<option value={String(a.id)}>@{a.alias}</option>
				{/each}
			</select>
			<ChevronDown
				size={14}
				strokeWidth={2}
				aria-hidden="true"
				class="pointer-events-none absolute right-2 text-dim"
			/>
		</label>

		<label
			class="relative flex h-9 items-center gap-1.5 rounded-xl border border-line bg-raised/70 px-2.5 text-sm text-dim"
		>
			<span class="font-mono text-[10px] tracking-[0.16em] uppercase">Sort</span>
			<select
				value={$ledgerFilters.sort}
				onchange={(e) => setLedgerFilters({ sort: e.currentTarget.value as LedgerSort })}
				class="h-full appearance-none border-0 bg-none bg-transparent py-0 pr-6 text-[13px] text-fg outline-none [color-scheme:inherit] [&>option]:bg-panel [&>option]:text-fg"
				aria-label="Sort trades"
			>
				<option value="newest">Newest</option>
				<option value="oldest">Oldest</option>
				<option value="net-desc">Net ↓</option>
				<option value="net-asc">Net ↑</option>
				<option value="r-desc">R ↓</option>
			</select>
			<ChevronDown
				size={14}
				strokeWidth={2}
				aria-hidden="true"
				class="pointer-events-none absolute right-2 text-dim"
			/>
		</label>

		{#if filtered.length > 0}
			<button
				type="button"
				onclick={() => (moveOpen = !moveOpen)}
				aria-expanded={moveOpen}
				aria-controls="trade-move-panel"
				class="flex h-9 items-center gap-1.5 rounded-xl border px-2.5 font-mono text-[11px] font-bold tracking-[0.08em] uppercase transition-all active:scale-95 {moveOpen
					? 'border-accent/60 bg-accent/15 text-accent'
					: 'border-line bg-raised/70 text-dim hover:border-accent/40 hover:text-fg'}"
			>
				Move{#if selectMode && selectedVisibleCount > 0}&nbsp;({selectedVisibleCount}){/if}
				<ChevronDown
					size={14}
					strokeWidth={2}
					aria-hidden="true"
					class="transition-transform duration-200 {moveOpen ? 'rotate-180' : ''}"
				/>
			</button>
		{/if}

		{#if moveOpen && filtered.length > 0}
			<div
				id="trade-move-panel"
				transition:slide={{ duration: 220 }}
				class="flex basis-full flex-wrap items-center gap-2 rounded-xl border border-line bg-raised/40 px-3 py-2"
			>
				<span class="num text-[12px] text-dim">{$tradesTotal} matching</span>
				<button
					type="button"
					onclick={toggleSelectMode}
					aria-pressed={selectMode}
					class="rounded-lg border px-2.5 py-1 font-mono text-[11px] font-bold tracking-[0.08em] uppercase transition-all active:scale-95 {selectMode
						? 'border-accent/60 bg-accent/15 text-accent'
						: 'border-line text-dim hover:border-accent/40 hover:text-fg'}"
				>
					{selectMode ? 'Done' : 'Select'}
				</button>
				{#if selectMode}
					<span class="num text-[12px] font-semibold text-fg">{selectedVisibleCount} selected</span>
					<button
						type="button"
						onclick={selectAllFiltered}
						disabled={allFilteredSelected}
						class="rounded-lg px-2 py-1 font-mono text-[11px] tracking-[0.06em] uppercase text-dim transition-colors hover:text-fg disabled:opacity-40"
					>
						All
					</button>
					<button
						type="button"
						onclick={clearSelection}
						disabled={selectedVisibleCount === 0}
						class="rounded-lg px-2 py-1 font-mono text-[11px] tracking-[0.06em] uppercase text-dim transition-colors hover:text-fg disabled:opacity-40"
					>
						None
					</button>
				{/if}
				<span class="font-mono text-[10px] tracking-[0.16em] text-dim uppercase">Move {selectMode ? 'selected' : 'shown'} to</span>
				<select bind:value={moveTarget} class="h-8 rounded-lg border border-line bg-panel px-2 font-mono text-[12px] text-fg outline-none" aria-label="Move target account">
					<option value="">Pick…</option>
					<option value="unassigned">Unassigned</option>
					{#each $accounts as a (a.id)}
						<option value={String(a.id)}>@{a.alias}</option>
					{/each}
				</select>
				<button type="button" onclick={() => void moveFiltered()} disabled={!moveTarget || moving || (selectMode && selectedVisibleCount === 0)} class="btn btn-ghost h-8 px-3 text-[12px] disabled:opacity-40">
					{moving ? 'Moving…' : selectMode ? `Move ${selectedVisibleCount}` : 'Move'}
				</button>
			</div>
		{/if}
	</div>

	{#if filtered.length === 0}
		<div class="card border-dashed px-6 py-12 text-center">
			<p class="display text-lg text-fg">No trades match these filters</p>
			<p class="mt-1.5 text-sm text-mut">Try a different symbol, tag, or status.</p>
		</div>
	{:else}
		<!-- Desktop ledger: div-grid, ONE shared .tgrid template for header + rows -->
		<div class="card hidden overflow-x-auto md:block" role="table" aria-label="Trade history">
			<div class="min-w-[940px]">
				<div role="row" class="tgrid sticky top-0 z-10 border-b border-line bg-panel">
					<span role="columnheader" class="flex items-center justify-center gap-1 px-1 py-2.5 text-center">
						{#if selectMode}
							<input
								type="checkbox"
								checked={allFilteredSelected}
								onchange={toggleAllFiltered}
								aria-label="Select all shown trades"
								class="h-4 w-4 shrink-0 cursor-pointer accent-[var(--c-accent)]"
							/>
						{:else}
							<span class="sr-only">Expand</span>
						{/if}
					</span>
					<span role="columnheader" class="thead px-3 py-2.5 text-left">Opened</span>
					<span role="columnheader" class="thead px-3 py-2.5 text-left">Symbol</span>
					<span role="columnheader" class="thead px-3 py-2.5 text-right">Entry → Exit</span>
					<span role="columnheader" class="thead px-3 py-2.5 text-right">Net</span>
					<span role="columnheader" class="thead px-3 py-2.5 text-right">R</span>
					<span role="columnheader" class="thead px-3 py-2.5 text-left">Tags</span>
					<span role="columnheader" class="thead px-3 py-2.5 text-right">Action</span>
				</div>
				{#each filtered as t, i (t.id)}
						<div
							role="row"
							tabindex={0}
							onclick={() => (selectMode ? toggleOne(t.id) : openTrade(t.id))}
							onkeydown={(e) => e.key === 'Enter' && (selectMode ? toggleOne(t.id) : openTrade(t.id))}
							class="tgrid trow anim-fade cursor-pointer row-line transition-colors duration-200 hover:bg-raised/50 focus-visible:outline-none {selectMode && selected.has(t.id) ? 'bg-accent/10' : ''}"
							style="animation-delay: {Math.min(i, 29) * 20}ms"
						>
							<span role="cell" class="flex items-center justify-center gap-1 px-1 py-2.5 text-center">
								{#if selectMode}
									<input
										type="checkbox"
										checked={selected.has(t.id)}
										onchange={() => toggleOne(t.id)}
										onclick={(e) => e.stopPropagation()}
										aria-label="Select trade {t.symbol ?? t.id}"
										class="h-4 w-4 shrink-0 cursor-pointer accent-[var(--c-accent)]"
									/>
								{/if}
								<button
									type="button"
									onclick={(e) => toggleExpand(t.id, e)}
									aria-label="Preview"
									aria-expanded={expanded.has(t.id)}
									class="grid h-6 w-6 shrink-0 place-items-center rounded-md text-dim transition-all duration-300 ease-spring hover:bg-raised hover:text-fg focus-visible:outline-none {expanded.has(
										t.id
									)
										? 'rotate-180 text-accent'
										: ''}"
								>
									<ChevronDown size={15} strokeWidth={1.8} aria-hidden="true" />
								</button>
							</span>
							<span role="cell" class="px-3 py-2.5 font-mono whitespace-nowrap text-[12.5px] text-mut">
								{fmtDateTime(t.timestamp_open)}
							</span>
							<span role="cell" class="truncate px-3 py-2.5 whitespace-nowrap">
								<span class="num text-[13px] font-semibold text-fg uppercase">{t.symbol ?? '—'}</span>
								<span
									class="ml-1.5 font-mono text-[10px] font-bold tracking-[0.12em] uppercase {(t.direction ?? '').toLowerCase() ===
									'sell'
										? 'text-loss'
										: 'text-win'}"
								>
									{t.direction ?? ''}
								</span>
								<span class="ml-1.5 font-mono text-[10px] text-dim">@{chipAlias($accountMap, t.account_id)}</span>
							</span>
							<span role="cell" class="px-3 py-2.5 text-right font-mono whitespace-nowrap text-[12.5px] tabular-nums text-mut">
								<span class="text-fg">{t.entry_price?.toFixed(2) ?? '—'}</span>
								<span class="px-1 text-dim">→</span>
								<span class="text-fg">{t.exit_price?.toFixed(2) ?? '—'}</span>
							</span>
							<span role="cell" class="px-3 py-2.5 text-right whitespace-nowrap">
								{#if isUnpriced(t)}
									<span
										class="num inline-block rounded-md bg-flat/12 px-1.5 py-0.5 text-[10px] font-bold tracking-[0.1em] uppercase text-flat"
										title="No contract or FX rate for this trade — its P&amp;L could not be priced in USD"
									>
										unpriced
									</span>
								{:else}
									<span
										class="num inline-block rounded-md px-1.5 py-0.5 text-[12.5px] font-semibold {toneBg[
											pnlTone(usdNet(t))
										]} {toneText[pnlTone(usdNet(t))]}"
										title={brokerLabel(t)}
									>
										{fmtMoney(usdNet(t))}
									</span>
								{/if}
							</span>
							<span role="cell" class="px-3 py-2.5 text-right font-mono whitespace-nowrap text-[12.5px] tabular-nums {toneText[rTone(t.r_multiple)]}">
								{fmtR(t.r_multiple)}
							</span>
							<span role="cell" class="min-w-0 px-3 py-2.5">
								<span class="flex flex-wrap gap-1">
									{#each t.tags as tag (tag.id)}
										<span class={tagChip(tag.name, tag.category)}>
											{tag.category === 'mistake' ? '!' : '#'}{tag.name}
										</span>
									{/each}
								</span>
							</span>
							<span role="cell" class="px-3 py-2.5 text-right whitespace-nowrap">
								{#if t.status === 'OPEN'}
									<button
										type="button"
										onclick={(e) => {
											e.stopPropagation();
											requestClose(t.id);
										}}
										class="rounded-lg border border-line px-2.5 py-1 font-mono text-[10px] font-bold tracking-[0.12em] uppercase text-loss transition-all duration-200 hover:border-loss/50 hover:bg-loss/12 focus-visible:outline-none active:scale-95"
									>
										Close
									</button>
								{/if}
							</span>
						</div>
						{#if expanded.has(t.id)}
							<div role="row" class="tgrid row-line">
								<span></span>
								<div role="cell" class="col-span-7 px-3 pt-0 pb-3">
									<div
										transition:slide={{ duration: 220 }}
										class="border-l-2 border-accent/40 pl-3 text-[13px] leading-relaxed text-mut"
									>
										{#if t.thesis}
											<p><span class="font-semibold text-fg">Thesis:</span> {t.thesis}</p>
										{/if}
										{#if t.review_notes}
											<p class="mt-1"><span class="font-semibold text-fg">Review:</span> {t.review_notes}</p>
										{/if}
										{#if !t.thesis && !t.review_notes}
											<p>No notes yet — open the trade to add a thesis.</p>
										{/if}
									</div>
								</div>
							</div>
						{/if}
					{/each}
			</div>
		</div>

		<!-- Mobile cards -->
		<div class="grid grid-cols-1 gap-2.5 md:hidden">
			{#each filtered as t, i (t.id)}
				<div
					role="button"
					tabindex={0}
					onclick={() => (selectMode ? toggleOne(t.id) : openTrade(t.id))}
					onkeydown={(e) => e.key === 'Enter' && (selectMode ? toggleOne(t.id) : openTrade(t.id))}
					class="card card-hover rise relative overflow-hidden p-3.5 text-left focus-visible:outline-none active:scale-[0.99] {selectMode && selected.has(t.id) ? 'border-accent/60' : ''}"
					style="animation-delay: {Math.min(i, 14) * 40}ms"
				>
					<span
						class="absolute inset-y-0 left-0 w-[3px] {pnlTone(usdNet(t)) === 'loss'
							? 'bg-loss/70'
							: pnlTone(usdNet(t)) === 'win'
								? 'bg-win/70'
								: 'bg-flat/70'}"
						aria-hidden="true"
					></span>
					<div class="flex items-center justify-between gap-2 pl-1.5">
						<span class="flex items-center gap-2">
							{#if selectMode}
								<input
									type="checkbox"
									checked={selected.has(t.id)}
									onchange={() => toggleOne(t.id)}
									onclick={(e) => e.stopPropagation()}
									aria-label="Select trade {t.symbol ?? t.id}"
									class="h-4 w-4 shrink-0 cursor-pointer accent-[var(--c-accent)]"
								/>
							{/if}
							<span class="num text-sm font-semibold text-fg uppercase">{t.symbol ?? '—'} <span class="font-mono text-[10px] font-normal text-dim normal-case">@{chipAlias($accountMap, t.account_id)}</span></span>
						</span>
						<span class="flex items-center gap-2">
							{#if isUnpriced(t)}
								<span
									class="num rounded-md bg-flat/12 px-1.5 py-0.5 text-[10px] font-bold tracking-[0.1em] uppercase text-flat"
									title="No contract or FX rate for this trade — its P&amp;L could not be priced in USD"
								>
									unpriced
								</span>
							{:else}
								<span class="num text-sm font-semibold {toneText[pnlTone(usdNet(t))]}" title={brokerLabel(t)}>
									{fmtMoney(usdNet(t))}
								</span>
							{/if}
							{#if t.status === 'OPEN'}
								<button
									type="button"
									onclick={(e) => {
										e.stopPropagation();
										requestClose(t.id);
									}}
									aria-label="Close trade"
									class="rounded-lg border border-line px-2.5 py-1 font-mono text-[10px] font-bold tracking-[0.12em] uppercase text-loss transition-all active:scale-95"
								>
									Close
								</button>
							{/if}
						</span>
					</div>
					<div class="mt-1.5 flex items-center justify-between pl-1.5 text-xs">
						<span class="text-dim">{fmtDateTime(t.timestamp_open)}</span>
						<span class="font-mono tabular-nums {toneText[rTone(t.r_multiple)]}">{fmtR(t.r_multiple)}</span>
					</div>
					{#if t.tags.length > 0}
						<span class="mt-2 flex flex-wrap gap-1 pl-1.5">
							{#each t.tags as tag (tag.id)}
								<span class={tagChip(tag.name, tag.category)}>
									{tag.category === 'mistake' ? '!' : '#'}{tag.name}
								</span>
							{/each}
						</span>
					{/if}
				</div>
			{/each}
		</div>

		<!-- The pager: the browser asks for one page at a time. -->
		<nav
			aria-label="Ledger pages"
			class="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-line pt-3"
		>
			<span class="num text-[11.5px] text-dim">
				Showing {showingFrom}–{showingTo} of {$tradesTotal}
			</span>
			<div class="flex items-center gap-2">
				<label class="flex items-center gap-1.5">
					<span class="font-mono text-[10px] tracking-[0.16em] text-dim uppercase">Rows</span>
					<select
						value={$tradesPageSize}
						onchange={(e) => setPageSize(Number(e.currentTarget.value))}
						class="h-8 rounded-lg border border-line bg-panel px-2 font-mono text-[12px] text-fg outline-none"
						aria-label="Rows per page"
					>
						<option value="25">25</option>
						<option value="50">50</option>
						<option value="100">100</option>
						<option value="200">200</option>
					</select>
				</label>
				<button
					type="button"
					onclick={() => gotoPage($tradesPage - 1, pages)}
					disabled={$tradesPage <= 1}
					class="btn btn-ghost h-8 px-2.5 text-[12px] disabled:opacity-40"
				>
					Prev
				</button>
				<span class="num text-[11.5px] whitespace-nowrap text-dim">Page {$tradesPage} of {pages}</span>
				<button
					type="button"
					onclick={() => gotoPage($tradesPage + 1, pages)}
					disabled={$tradesPage >= pages}
					class="btn btn-ghost h-8 px-2.5 text-[12px] disabled:opacity-40"
				>
					Next
				</button>
			</div>
		</nav>
	{/if}
</section>
