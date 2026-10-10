<script lang="ts">
	import { onMount } from 'svelte';
	import { Pencil, Plus, Trash2, X } from 'lucide-svelte';
	import { fade, scale } from 'svelte/transition';
	import PageHead from '$lib/components/PageHead.svelte';
	import StateBlock from '$lib/components/StateBlock.svelte';
	import { api, errMsg, type AccountDto } from '$lib/api';
	import { accounts, accountsError, accountsLoading, loadAccounts } from '$lib/stores/accounts';
	import { toasts } from '$lib/stores/toast';
	import { FADE, MODAL } from '$lib/utils/transitions';

	const PHASES = ['challenge1', 'phase2', 'funded', 'personal'] as const;

	let modal = $state<null | { editing: AccountDto | null }>(null);
	let saving = $state(false);
	let formError = $state<string | null>(null);

	let fFirm = $state('');
	let fAlias = $state('');
	let fLogin = $state('');
	let fPhase = $state<string>('funded');
	let fStart = $state('100000');
	let fDaily = $state('5000');
	let fDailyBasis = $state('balance');
	let fMax = $state('10000');
	let fMaxMode = $state('static');
	let fTrailing = $state('balance_peak');
	let fTarget = $state('10000');
	let fStatus = $state('active');

	let confirmDelete = $state<number | null>(null);

	onMount(() => {
		void loadAccounts();
	});

	function openCreate(): void {
		fFirm = '';
		fAlias = '';
		fLogin = '';
		fPhase = 'funded';
		fStart = '100000';
		fDaily = '5000';
		fDailyBasis = 'balance';
		fMax = '10000';
		fMaxMode = 'static';
		fTrailing = 'balance_peak';
		fTarget = '10000';
		fStatus = 'active';
		formError = null;
		modal = { editing: null };
	}

	function openEdit(a: AccountDto): void {
		fFirm = a.firm;
		fAlias = a.alias;
		fLogin = a.login ?? '';
		fPhase = a.phase;
		fStart = String(a.start_balance);
		fDaily = String(a.daily_loss_limit);
		fDailyBasis = a.daily_basis;
		fMax = String(a.max_loss_limit);
		fMaxMode = a.max_mode;
		fTrailing = a.trailing_ref;
		fTarget = a.profit_target === null ? '' : String(a.profit_target);
		fStatus = a.status;
		formError = null;
		modal = { editing: a };
	}

	const num = (v: string): number | null => {
		if (v.trim() === '') return null;
		const n = Number(v);
		return Number.isFinite(n) ? n : NaN;
	};

	async function submit(e: SubmitEvent): Promise<void> {
		e.preventDefault();
		formError = null;
		const alias = fAlias.trim().toLowerCase();
		if (!/^[a-z0-9][a-z0-9\-_]{1,23}$/.test(alias)) {
			formError = 'Alias must be lowercase a-z0-9-_, 2-24 chars (e.g. ftmo100k-f1).';
			return;
		}
		const start = num(fStart) ?? 0;
		const daily = num(fDaily) ?? 0;
		const max = num(fMax) ?? 0;
		const targetRaw = fTarget.trim() === '' ? null : num(fTarget);
		if ([start, daily, max].some((n) => !Number.isFinite(n) || n < 0) || (targetRaw !== null && (!Number.isFinite(targetRaw) || targetRaw < 0))) {
			formError = 'Balances, limits and target must be numbers >= 0.';
			return;
		}
		const payload = {
			firm: fFirm.trim(),
			alias,
			login: fLogin.trim() || null,
			phase: fPhase,
			start_balance: start,
			daily_loss_limit: daily,
			daily_basis: fDailyBasis,
			max_loss_limit: max,
			max_mode: fMaxMode,
			trailing_ref: fTrailing,
			profit_target: targetRaw,
			status: fStatus
		};
		saving = true;
		try {
			if (modal?.editing) {
				const updated = await api.updateAccount(modal.editing.id, payload);
				accounts.update((l) => l.map((x) => (x.id === updated.id ? updated : x)));
				toasts.push('success', `Account @${updated.alias} updated.`);
			} else {
				const created = await api.createAccount(payload);
				accounts.update((l) => [...l, created].sort((a, b) => a.alias.localeCompare(b.alias)));
				toasts.push('success', `Account @${created.alias} created.`);
			}
			modal = null;
		} catch (err) {
			formError = errMsg(err);
		} finally {
			saving = false;
		}
	}

	async function doDelete(id: number): Promise<void> {
		if (confirmDelete !== id) {
			confirmDelete = id;
			setTimeout(() => {
				if (confirmDelete === id) confirmDelete = null;
			}, 4000);
			return;
		}
		try {
			await api.deleteAccount(id);
			accounts.update((l) => l.filter((x) => x.id !== id));
			confirmDelete = null;
			toasts.push('success', 'Account deleted — its trades are now unassigned.');
		} catch (err) {
			toasts.push('error', `Delete failed — ${errMsg(err)}`);
		}
	}

	const field = 'field font-mono text-[13px]';
	const label = 'flex flex-col gap-1.5 text-[11px] font-medium tracking-[0.14em] uppercase text-dim';
</script>

<svelte:head>
	<title>Accounts · Trading Journal</title>
</svelte:head>

<PageHead eyebrow="workspace" title="Accounts" meta="{$accounts.length} prop accounts">
	<button type="button" onclick={openCreate} class="btn btn-primary h-10 px-4 text-sm">
		<Plus size={16} strokeWidth={2.2} aria-hidden="true" />
		Add account
	</button>
</PageHead>

{#if $accountsLoading}
	<div class="grid grid-cols-1 gap-4 md:grid-cols-2">
		{#each Array(4) as _}
			<div class="skeleton h-44"></div>
		{/each}
	</div>
{:else if $accountsError}
	<StateBlock
		kind="error"
		title="Couldn't reach the backend"
		body="{$accountsError} — start the API and retry."
		actionLabel="Retry"
		onAction={() => void loadAccounts()}
	/>
{:else if $accounts.length === 0}
	<StateBlock
		title="No accounts yet"
		body="Add your first prop account — e.g. FTMO @ftmo100k-f1 — then tag trades with @alias in Telegram or the dropdown here."
		actionLabel="Add account"
		onAction={openCreate}
	/>
{:else}
	<div class="grid grid-cols-1 gap-4 md:grid-cols-2">
		{#each $accounts as a (a.id)}
			<article class="card rise p-5" aria-label="Account @{a.alias}">
				<div class="flex flex-wrap items-center gap-2">
					<h2 class="num text-lg font-semibold text-fg">@{a.alias}</h2>
					<span class="rounded-lg bg-raised px-2 py-0.5 font-mono text-[10px] font-semibold tracking-[0.14em] text-mut uppercase">
						{a.firm || 'no firm'} · {a.phase}
					</span>
					<span class="rounded-lg px-2 py-0.5 font-mono text-[10px] font-semibold tracking-[0.14em] uppercase {a.status === 'active' ? 'bg-win/12 text-win' : a.status === 'archived' ? 'bg-flat/12 text-flat' : 'bg-loss/12 text-loss'}">
						{a.status}
					</span>
					<span class="ml-auto flex items-center gap-1.5">
						<button type="button" onclick={() => openEdit(a)} aria-label="Edit @{a.alias}" class="btn-icon h-8 w-8">
							<Pencil size={15} strokeWidth={1.8} aria-hidden="true" />
						</button>
						<button type="button" onclick={() => void doDelete(a.id)} aria-label="Delete @{a.alias}" class="btn-icon h-8 w-8 text-loss">
							<Trash2 size={15} strokeWidth={1.8} aria-hidden="true" />
						</button>
					</span>
				</div>
				{#if confirmDelete === a.id}
					<p class="mt-2 text-[13px] font-medium text-loss" role="alert">
						Delete @{a.alias}? Its trades become unassigned. Tap delete again to confirm.
					</p>
				{/if}
				<dl class="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
					<div><dt class="eyebrow">Start</dt><dd class="num mt-1 text-sm text-fg tabular-nums">{a.start_balance.toLocaleString()}</dd></div>
					<div><dt class="eyebrow">Daily max</dt><dd class="num mt-1 text-sm text-fg tabular-nums">{a.daily_loss_limit.toLocaleString()} <span class="text-dim">({a.daily_basis})</span></dd></div>
					<div><dt class="eyebrow">Max loss</dt><dd class="num mt-1 text-sm text-fg tabular-nums">{a.max_loss_limit.toLocaleString()} <span class="text-dim">({a.max_mode})</span></dd></div>
					<div><dt class="eyebrow">Target</dt><dd class="num mt-1 text-sm text-fg tabular-nums">{a.profit_target ?? '—'}</dd></div>
				</dl>
				<p class="num mt-3 border-t border-line pt-2.5 text-[11px] text-dim">
					{a.open_trades} open · {a.total_trades} total{#if a.login} · login {a.login}{/if}
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
		aria-label={modal.editing ? 'Edit account' : 'Add account'}
	>
		<div transition:scale={MODAL} class="card w-full max-w-lg overflow-hidden p-0 shadow-pop">
			<div class="flex items-center gap-2.5 border-b border-line px-5 py-4">
				<h2 class="display text-xl text-fg">{modal.editing ? `Edit @${modal.editing.alias}` : 'Add account'}</h2>
				<button type="button" onclick={() => (modal = null)} aria-label="Close" class="btn-icon ml-auto h-8 w-8">
					<X size={17} strokeWidth={1.8} aria-hidden="true" />
				</button>
			</div>
			<form class="px-5 py-4" onsubmit={submit}>
				<div class="grid grid-cols-2 gap-3">
					<label class={label}>Firm<input type="text" bind:value={fFirm} placeholder="FTMO" class={field} /></label>
					<label class={label}>Alias<input type="text" bind:value={fAlias} placeholder="ftmo100k-f1" autocomplete="off" class="{field} lowercase" /></label>
					<label class={label}>Login <span class="normal-case tracking-normal text-dim">(optional)</span><input type="text" bind:value={fLogin} placeholder="88421" class={field} /></label>
					<label class={label}>Phase
						<select bind:value={fPhase} class={field}>
							{#each PHASES as p}<option value={p}>{p}</option>{/each}
						</select>
					</label>
					<label class={label}>Start balance<input type="number" bind:value={fStart} min="0" step="any" class={field} /></label>
					<label class={label}>Profit target <span class="normal-case tracking-normal text-dim">(empty = none)</span><input type="number" bind:value={fTarget} min="0" step="any" class={field} /></label>
					<label class={label}>Daily max loss $<input type="number" bind:value={fDaily} min="0" step="any" class={field} /></label>
					<label class={label}>Daily basis
						<select bind:value={fDailyBasis} class={field}>
							<option value="balance">balance (closed)</option>
							<option value="equity">equity (floating)</option>
						</select>
					</label>
					<label class={label}>Max loss $<input type="number" bind:value={fMax} min="0" step="any" class={field} /></label>
					<label class={label}>Max mode
						<select bind:value={fMaxMode} class={field}>
							<option value="static">static (from start)</option>
							<option value="trailing">trailing (from peak)</option>
						</select>
					</label>
					{#if fMaxMode === 'trailing'}
						<label class={label}>Trails on
							<select bind:value={fTrailing} class={field}>
								<option value="balance_peak">closed balance peak</option>
								<option value="equity_peak">equity peak</option>
							</select>
						</label>
					{/if}
					<label class={label}>Status
						<select bind:value={fStatus} class={field}>
							<option value="active">active</option>
							<option value="breach">breach</option>
							<option value="passed">passed</option>
							<option value="archived">archived</option>
						</select>
					</label>
				</div>
				<p class="num mt-3 text-[11px] text-dim">Limits are absolute $ — % off start is resolved at input time. Day resets at UTC midnight.</p>
				{#if formError}<p class="mt-3 text-[13px] font-medium text-loss" role="alert">{formError}</p>{/if}
				<div class="mt-5 flex justify-end gap-2 border-t border-line pt-4">
					<button type="button" onclick={() => (modal = null)} class="btn btn-ghost h-10 px-4 text-sm">Cancel</button>
					<button type="submit" disabled={saving} class="btn btn-primary h-10 px-5 text-sm">
						{saving ? 'Saving…' : modal.editing ? 'Save changes' : 'Add account'}
					</button>
				</div>
			</form>
		</div>
	</div>
{/if}
