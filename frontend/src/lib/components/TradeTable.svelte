<script lang="ts">
	import { ChevronDown, Search } from 'lucide-svelte';
	import { slide } from 'svelte/transition';
	import { openTrade, requestClose, trades } from '$lib/stores/trades';
	import { fmtDateTime, fmtMoney, fmtR, pnlTone, toneBg, toneText } from '$lib/utils/format';
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
			target &&
			(target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT');
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
		return `rounded-md px-1.5 py-0.5 font-mono text-[10.5px] ${
			category === 'mistake' ? 'tag-mistake' : 'tag-setup'
		}`;
	}

	const th =
		'px-3 py-2.5 text-left font-mono text-[10px] font-medium tracking-[0.16em] uppercase text-dim';
</script>

<svelte:window onkeydown={onGlobalKey} />

<section aria-label="Trade history" class="rise mt-9" style="animation-delay: 140ms">
	<div class="mb-3 flex flex-wrap items-center gap-2">
		<div
			class="flex rounded-xl border border-line bg-raised/50 p-1"
			role="tablist"
			aria-label="Status filter"
		>
			{#each (['ALL', 'OPEN', 'CLOSED'] as StatusFilter[]) as s}
				<button
					type="button"
					role="tab"
					aria-selected={status === s}
					onclick={() => (status = s)}
					class="chip px-3 py-1.5 font-mono text-xs tabular-nums {status === s ? 'font-semibold' : ''}"
					data-active={status === s}
				>
					{s === 'ALL' ? 'All' : s === 'OPEN' ? 'Open' : 'Closed'}
					<span class="ml-1 opacity-60 tabular-nums">{counts[s]}</span>
				</button>
			{/each}
		</div>

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
				bind:value={query}
				placeholder="Symbol or ID…  ( / )"
				class="field h-9 pl-8 text-[13px]"
			/>
		</label>

		<label class="relative flex-1 sm:max-w-44">
			<span
				class="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 font-mono text-xs text-dim"
				aria-hidden="true">#</span>
			<input type="search" bind:value={tagQuery} placeholder="Tag…" class="field h-9 pl-7 font-mono text-[13px]" />
		</label>

		<label
			class="relative flex h-9 items-center gap-1.5 rounded-xl border border-line bg-raised/70 px-2.5 text-sm text-dim"
		>
			<span class="font-mono text-[10px] tracking-[0.16em] uppercase">Sort</span>
			<select
				bind:value={sort}
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
	</div>

	{#if filtered.length === 0}
		<div class="card border-dashed px-6 py-12 text-center">
			<p class="display text-lg text-fg">No trades match these filters</p>
			<p class="mt-1.5 text-sm text-mut">Try a different symbol, tag, or status.</p>
		</div>
	{:else}
		<!-- Desktop table -->
		<div class="card hidden overflow-x-auto md:block">
			<table class="w-full min-w-[820px] border-collapse text-sm">
				<thead>
					<tr class="border-b border-line">
						<th class="{th} w-8"></th>
						<th class={th}>Opened</th>
						<th class={th}>Symbol</th>
						<th class="{th} text-right">Entry → Exit</th>
						<th class="{th} text-right">Net</th>
						<th class="{th} text-right">R</th>
						<th class={th}>Tags</th>
						<th class="{th} text-right">Action</th>
					</tr>
				</thead>
				<tbody>
					{#each filtered as t (t.id)}
						<tr
							onclick={() => openTrade(t.id)}
							class="trow cursor-pointer row-line transition-colors duration-200 hover:bg-raised/50 focus-visible:outline-none"
						>
							<td class="px-3 py-2.5">
								<button
									type="button"
									onclick={(e) => toggleExpand(t.id, e)}
									aria-label="Preview"
									aria-expanded={expanded.has(t.id)}
									class="grid h-6 w-6 place-items-center rounded-md text-dim transition-all duration-300 ease-spring hover:bg-raised hover:text-fg focus-visible:outline-none {expanded.has(
										t.id
									)
										? 'rotate-180 text-accent'
										: ''}"
								>
									<ChevronDown size={15} strokeWidth={1.8} aria-hidden="true" />
								</button>
							</td>
							<td class="px-3 py-2.5 whitespace-nowrap font-mono text-[12.5px] text-mut">
								{fmtDateTime(t.timestamp_open)}
							</td>
							<td class="px-3 py-2.5">
								<span class="num text-[13px] font-semibold text-fg uppercase">{t.symbol ?? '—'}</span>
								<span
									class="ml-1.5 font-mono text-[10px] font-bold tracking-[0.12em] uppercase {(t.direction ?? '').toLowerCase() ===
									'sell'
										? 'text-loss'
										: 'text-win'}"
								>
									{t.direction ?? ''}
								</span>
							</td>
							<td class="px-3 py-2.5 text-right font-mono text-[12.5px] tabular-nums text-mut">
								<span class="text-fg">{t.entry_price?.toFixed(2) ?? '—'}</span>
								<span class="px-1 text-dim">→</span>
								<span class="text-fg">{t.exit_price?.toFixed(2) ?? '—'}</span>
							</td>
							<td class="px-3 py-2.5 text-right">
								<span
									class="num inline-block rounded-md px-1.5 py-0.5 text-[12.5px] font-semibold {toneBg[
										pnlTone(t.net_pnl)
									]} {toneText[pnlTone(t.net_pnl)]}"
								>
									{fmtMoney(t.net_pnl)}
								</span>
							</td>
							<td class="px-3 py-2.5 text-right font-mono text-[12.5px] tabular-nums {toneText[pnlTone(t.r_multiple)]}">
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
							<td class="px-3 py-2.5 text-right">
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
							</td>
						</tr>
						{#if expanded.has(t.id)}
							<tr class="row-line">
								<td></td>
								<td colspan={7} class="px-3 pt-0 pb-3">
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
				<div
					role="button"
					tabindex={0}
					onclick={() => openTrade(t.id)}
					onkeydown={(e) => e.key === 'Enter' && openTrade(t.id)}
					class="card card-hover relative overflow-hidden p-3.5 text-left focus-visible:outline-none active:scale-[0.99]"
				>
					<span
						class="absolute inset-y-0 left-0 w-[3px] {pnlTone(t.net_pnl) === 'loss'
							? 'bg-loss/70'
							: pnlTone(t.net_pnl) === 'win'
								? 'bg-win/70'
								: 'bg-flat/50'}"
						aria-hidden="true"
					></span>
					<div class="flex items-center justify-between gap-2 pl-1.5">
						<span class="num text-sm font-semibold text-fg uppercase">{t.symbol ?? '—'}</span>
						<span class="flex items-center gap-2">
							<span class="num text-sm font-semibold {toneText[pnlTone(t.net_pnl)]}">
								{fmtMoney(t.net_pnl)}
							</span>
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
						<span class="font-mono tabular-nums {toneText[pnlTone(t.r_multiple)]}">{fmtR(t.r_multiple)}</span>
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
	{/if}
</section>
