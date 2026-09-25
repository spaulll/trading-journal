<script lang="ts">
	import { ChevronDown, Search } from 'lucide-svelte';
	import { slide } from 'svelte/transition';
	import { trades, openTrade } from '$lib/stores/trades';
	import { fmtDateTime, fmtMoney, fmtR, pnlTone, toneText } from '$lib/utils/format';
	import type { TradeDto } from '$lib/api';

	type StatusFilter = 'ALL' | 'OPEN' | 'CLOSED';
	type SortKey = 'newest' | 'oldest' | 'net-desc' | 'net-asc' | 'r-desc';

	let status: StatusFilter = $state('ALL');
	let query = $state('');
	let tagQuery = $state('');
	let sort: SortKey = $state('newest');
	let searchEl: HTMLInputElement | null = $state(null);
	let expanded = $state<Set<number>>(new Set());

	function onGlobalKey(e: KeyboardEvent): void {
		const target = e.target as HTMLElement | null;
		const typing =
			target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT');
		if (e.key === '/' && !typing) {
			e.preventDefault();
			searchEl?.focus();
		}
	}

	function sortTrades(list: TradeDto[]): TradeDto[] {
		const byTime = (t: TradeDto) => t.timestamp_open ?? t.created_at;
		const numLast = (v: number | null | undefined, desc: boolean) =>
			v === null || v === undefined ? (desc ? -Infinity : Infinity) : v;
		const next = [...list];
		switch (sort) {
			case 'oldest':
				return next.sort((a, b) => byTime(a).localeCompare(byTime(b)));
			case 'net-desc':
				return next.sort((a, b) => numLast(b.net_pnl, true) - numLast(a.net_pnl, true));
			case 'net-asc':
				return next.sort((a, b) => numLast(a.net_pnl, false) - numLast(b.net_pnl, false));
			case 'r-desc':
				return next.sort((a, b) => numLast(b.r_multiple, true) - numLast(a.r_multiple, true));
			default:
				return next.sort((a, b) => byTime(b).localeCompare(byTime(a)));
		}
	}

	const filtered = $derived.by(() => {
		const q = query.trim().toLowerCase();
		const tq = tagQuery.trim().toLowerCase().replace(/^[#!]/, '');
		const list = $trades.filter((t) => {
			if (status !== 'ALL' && t.status !== status) return false;
			if (q && !(t.symbol ?? '').toLowerCase().includes(q) && !(t.trade_id ?? '').toLowerCase().includes(q))
				return false;
			if (tq && !t.tags.some((tag) => tag.name.toLowerCase().includes(tq))) return false;
			return true;
		});
		return sortTrades(list);
	});

	const counts = $derived.by(() => ({
		ALL: $trades.length,
		OPEN: $trades.filter((t) => t.status === 'OPEN').length,
		CLOSED: $trades.filter((t) => t.status !== 'OPEN').length
	}));

	function toggleExpand(id: number, e: MouseEvent): void {
		e.stopPropagation();
		expanded = new Set(expanded.has(id) ? [...expanded].filter((x) => x !== id) : [...expanded, id]);
	}

	function tagChip(name: string, category: string): string {
		const base = 'rounded-md px-1.5 py-0.5 font-mono text-[11px] tabular-nums';
		return category === 'mistake'
			? `${base} bg-rose-500/10 text-rose-600 dark:text-rose-400`
			: `${base} bg-emerald-500/10 text-emerald-600 dark:text-emerald-400`;
	}

	function dirBadge(t: TradeDto): string {
		return (t.direction ?? '').toLowerCase() === 'sell'
			? 'text-rose-600 dark:text-rose-400'
			: 'text-emerald-600 dark:text-emerald-400';
	}
</script>

<svelte:window onkeydown={onGlobalKey} />

<section aria-label="Trade history" class="mt-8">
	<div class="mb-3 flex flex-wrap items-center gap-2">
		<div class="flex rounded-lg border border-slate-200 p-0.5 dark:border-slate-800" role="tablist" aria-label="Status filter">
			{#each (['ALL', 'OPEN', 'CLOSED'] as StatusFilter[]) as s}
				<button
					type="button"
					role="tab"
					aria-selected={status === s}
					onclick={() => (status = s)}
					class="rounded-md px-3 py-1.5 font-mono text-xs transition-colors duration-150 {status === s
						? 'bg-slate-900 font-medium text-white dark:bg-white dark:text-slate-900'
						: 'text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white'}"
				>
					{s === 'ALL' ? 'All' : s === 'OPEN' ? 'Open' : 'Closed'}
					<span class="ml-1 opacity-60 tabular-nums">{counts[s]}</span>
				</button>
			{/each}
		</div>
		<label class="relative ml-auto flex-1 sm:max-w-56">
			<Search size={14} class="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-slate-400" />
			<input
				type="search"
				bind:this={searchEl}
				bind:value={query}
				placeholder="Symbol or ID…  ( / )"
				class="h-9 w-full rounded-lg border border-slate-200 bg-transparent pr-2 pl-8 text-sm outline-none placeholder:text-slate-400 focus:border-emerald-500 dark:border-slate-800"
			/>
		</label>
		<label class="relative flex-1 sm:max-w-44">
			<span class="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 font-mono text-xs text-slate-400">#</span>
			<input
				type="search"
				bind:value={tagQuery}
				placeholder="Tag…"
				class="h-9 w-full rounded-lg border border-slate-200 bg-transparent pr-2 pl-7 font-mono text-sm outline-none placeholder:text-slate-400 focus:border-emerald-500 dark:border-slate-800"
			/>
		</label>
		<label class="flex h-9 items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
			<span class="font-mono text-[11px] uppercase">Sort</span>
			<select
				bind:value={sort}
				class="bg-transparent text-sm text-slate-700 outline-none dark:bg-transparent dark:text-slate-200"
				aria-label="Sort trades"
			>
				<option value="newest">Newest</option>
				<option value="oldest">Oldest</option>
				<option value="net-desc">Net ↓</option>
				<option value="net-asc">Net ↑</option>
				<option value="r-desc">R ↓</option>
			</select>
		</label>
	</div>

	{#if filtered.length === 0}
		<p class="rounded-xl border border-dashed border-slate-300 px-6 py-10 text-center text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
			No trades match these filters.
		</p>
	{:else}
		<!-- Desktop table -->
		<div class="hidden overflow-x-auto rounded-xl border border-slate-200 md:block dark:border-slate-800">
			<table class="w-full min-w-[760px] border-collapse text-sm">
				<thead>
					<tr class="border-b border-slate-200 text-left font-mono text-[11px] text-slate-400 uppercase dark:border-slate-800 dark:text-slate-500">
						<th class="w-8 px-3 py-2.5"></th>
						<th class="px-3 py-2.5">Opened</th>
						<th class="px-3 py-2.5">Symbol</th>
						<th class="px-3 py-2.5 text-right">Entry → Exit</th>
						<th class="px-3 py-2.5 text-right">Net</th>
						<th class="px-3 py-2.5 text-right">R</th>
						<th class="px-3 py-2.5">Tags</th>
					</tr>
				</thead>
				<tbody>
					{#each filtered as t (t.id)}
						<tr
							onclick={() => openTrade(t.id)}
							class="cursor-pointer border-b border-slate-100 transition-all duration-150 last:border-0 hover:-translate-y-px hover:bg-slate-50 dark:border-slate-800/60 dark:hover:bg-surface-800/60"
						>
							<td class="px-3 py-2.5">
								<button
									type="button"
									onclick={(e) => toggleExpand(t.id, e)}
									aria-label="Preview"
									class="grid h-6 w-6 place-items-center rounded text-slate-400 transition-transform duration-150 hover:text-slate-700 {expanded.has(t.id)
										? 'rotate-180'
										: ''} dark:hover:text-slate-200"
								>
									<ChevronDown size={15} />
								</button>
							</td>
							<td class="px-3 py-2.5 whitespace-nowrap text-slate-500 dark:text-slate-400">
								{fmtDateTime(t.timestamp_open)}
							</td>
							<td class="px-3 py-2.5">
								<span class="font-mono font-medium uppercase">{t.symbol ?? '—'}</span>
								<span class="ml-1.5 font-mono text-[11px] font-medium uppercase {dirBadge(t)}">
									{t.direction ?? ''}
								</span>
							</td>
							<td class="px-3 py-2.5 text-right font-mono tabular-nums">
								{t.entry_price?.toFixed(2) ?? '—'} → {t.exit_price?.toFixed(2) ?? '—'}
							</td>
							<td class="px-3 py-2.5 text-right font-mono font-medium tabular-nums {toneText[pnlTone(t.net_pnl)]}">
								{fmtMoney(t.net_pnl)}
							</td>
							<td class="px-3 py-2.5 text-right font-mono tabular-nums {toneText[pnlTone(t.r_multiple)]}">
								{fmtR(t.r_multiple)}
							</td>
							<td class="px-3 py-2.5">
								<span class="flex flex-wrap gap-1">
									{#each t.tags as tag (tag.id)}
										<span class={tagChip(tag.name, tag.category)}>
											{tag.category === 'mistake' ? '!' : '#'}{tag.name}
										</span>
									{/each}
								</span>
							</td>
						</tr>
						{#if expanded.has(t.id)}
							<tr class="border-b border-slate-100 dark:border-slate-800/60">
								<td></td>
								<td colspan={6} class="px-3 pt-0 pb-3">
									<div transition:slide={{ duration: 180 }} class="text-[13px] text-slate-500 dark:text-slate-400">
										{#if t.thesis}<p><span class="font-medium text-slate-700 dark:text-slate-300">Thesis:</span> {t.thesis}</p>{/if}
										{#if t.review_notes}<p class="mt-1"><span class="font-medium text-slate-700 dark:text-slate-300">Review:</span> {t.review_notes}</p>{/if}
										{#if !t.thesis && !t.review_notes}<p>No notes yet — open the trade to add a thesis.</p>{/if}
									</div>
								</td>
							</tr>
						{/if}
					{/each}
				</tbody>
			</table>
		</div>

		<!-- Mobile cards -->
		<div class="grid grid-cols-1 gap-2.5 md:hidden">
			{#each filtered as t (t.id)}
				<button
					type="button"
					onclick={() => openTrade(t.id)}
					class="rounded-xl border border-slate-200 bg-white p-3.5 text-left transition-all duration-150 active:scale-[0.99] dark:border-slate-800 dark:bg-surface-900"
				>
					<div class="flex items-center justify-between gap-2">
						<span class="font-mono text-sm font-semibold uppercase">{t.symbol ?? '—'}</span>
						<span class="font-mono text-sm font-medium tabular-nums {toneText[pnlTone(t.net_pnl)]}">
							{fmtMoney(t.net_pnl)}
						</span>
					</div>
					<div class="mt-1.5 flex items-center justify-between text-xs">
						<span class="text-slate-500 dark:text-slate-400">{fmtDateTime(t.timestamp_open)}</span>
						<span class="font-mono tabular-nums {toneText[pnlTone(t.r_multiple)]}">{fmtR(t.r_multiple)}</span>
					</div>
					{#if t.tags.length > 0}
						<span class="mt-2 flex flex-wrap gap-1">
							{#each t.tags as tag (tag.id)}
								<span class={tagChip(tag.name, tag.category)}>
									{tag.category === 'mistake' ? '!' : '#'}{tag.name}
								</span>
							{/each}
						</span>
					{/if}
				</button>
			{/each}
		</div>
	{/if}
</section>
