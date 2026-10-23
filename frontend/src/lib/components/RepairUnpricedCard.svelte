<script lang="ts">
	import { Wrench } from 'lucide-svelte';
	import { api, errMsg, type RepairRowDto, type RepairUnpricedResultDto } from '$lib/api';
	import { toasts } from '$lib/stores/toast';
	import { fmtNum } from '$lib/utils/format';

	let { onrepaired }: { onrepaired?: () => void } = $props();

	let checking = $state(false);
	let applying = $state(false);
	let result = $state<RepairUnpricedResultDto | null>(null);
	let error = $state<string | null>(null);

	const visible = $derived(result ? result.results.slice(0, 6) : []);
	const busy = $derived(checking || applying);

	async function check(): Promise<void> {
		if (busy) return;
		checking = true;
		error = null;
		try {
			result = await api.repairUnpriced(false);
		} catch (e) {
			error = errMsg(e);
		} finally {
			checking = false;
		}
	}

	async function apply(): Promise<void> {
		if (busy || !result || result.repairable === 0) return;
		applying = true;
		error = null;
		try {
			const res = await api.repairUnpriced(true);
			result = res;
			toasts.push(
				'success',
				`Priced ${res.repaired} trade${res.repaired === 1 ? '' : 's'}; net = gross − fees restored.`
			);
			onrepaired?.();
		} catch (e) {
			error = errMsg(e);
		} finally {
			applying = false;
		}
	}

	function label(action: RepairRowDto['action']): string {
		if (action === 'repaired') return 'priced';
		if (action === 'would_repair') return 'can price';
		return action;
	}

	function tone(action: RepairRowDto['action']): string {
		return action === 'repaired' || action === 'would_repair' ? 'text-accent' : 'text-dim';
	}
</script>

<section aria-label="Ledger repair" class="card rise flex h-full flex-col p-4">
	<div class="flex flex-wrap items-center gap-x-2 gap-y-1">
		<Wrench size={16} strokeWidth={2} aria-hidden="true" class="text-accent" />
		<h2 class="text-[15px] font-semibold text-fg">Ledger repair</h2>
		<span class="num text-[11px] text-dim">Missing gross P&amp;L · symbol registry</span>
	</div>

	<p class="mt-1.5 text-[12px] leading-snug text-mut">
		Reprices closed trades missing gross from the symbol registry. Dry run until you apply.
	</p>
	<p class="num mt-1 text-[10px] text-dim">No exit price → skipped · entered net → kept</p>

	<div class="mt-3 flex flex-wrap items-center gap-2 xl:mt-auto">
		<button type="button" onclick={() => void check()} disabled={busy} class="btn h-9 px-4 text-[13px] disabled:opacity-50">
			{checking ? 'Checking…' : result ? 'Check again' : 'Check unpriced trades'}
		</button>
		{#if result && !result.apply && result.repairable > 0}
			<button
				type="button"
				onclick={() => void apply()}
				disabled={busy}
				class="btn btn-primary h-9 px-4 text-[13px] disabled:opacity-50"
			>
				{applying ? 'Applying…' : `Apply repair · ${result.repairable}`}
			</button>
		{/if}
	</div>

	{#if error}
		<p role="alert" class="mt-3 rounded-xl border border-loss/40 bg-loss/8 px-3 py-2 text-[13px] text-loss">
			Repair failed — {error}
		</p>
	{:else if result}
		<div class="mt-3 rounded-xl border border-line bg-raised/30 px-4 py-3" aria-label="Repair result">
			{#if result.scanned === 0}
				<p class="text-[13px] text-mut">No closed trade is missing gross P&amp;L.</p>
			{:else if result.apply}
				<p class="num text-[13px] font-semibold text-fg">
					{result.repaired} priced · {result.skipped} skipped · {result.unpriced} unpriced
				</p>
			{:else}
				<p class="num text-[13px] font-semibold text-fg">
					{result.repairable} of {result.scanned} can be priced · {result.skipped} skipped · {result.unpriced} unpriced
				</p>
			{/if}
			{#if result.kept_net > 0}
				<p class="num mt-0.5 text-[11px] text-dim">{result.kept_net} kept the net you entered.</p>
			{/if}
			{#if visible.length > 0}
				<ul class="mt-2 border-t border-line/60">
					{#each visible as row (row.ticket)}
						<li class="border-b border-line/60 py-1.5 last:border-0">
							<div class="flex min-w-0 flex-wrap items-baseline gap-x-2">
								<span class="num min-w-0 break-all text-[11px] text-fg">{row.ticket}</span>
								<span class="text-[10px] uppercase tracking-wide {tone(row.action)}">{label(row.action)}</span>
							</div>
							<div class="mt-0.5 min-w-0">
								{#if row.reason}
									<span class="block break-words text-[11px] text-dim">{row.reason}</span>
								{:else}
									<span class="num block text-[11px] text-mut">
										gross {fmtNum(row.gross_pnl)} · net {fmtNum(row.net_pnl)}{row.kept_net ? ' · net kept' : ''}
									</span>
								{/if}
							</div>
						</li>
					{/each}
				</ul>
				{#if result.results.length > visible.length}
					<p class="num mt-1 text-[10px] text-dim">+{result.results.length - visible.length} more</p>
				{/if}
			{/if}
		</div>
	{/if}
</section>
