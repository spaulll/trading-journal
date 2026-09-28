<script lang="ts">
	import { fade, fly } from 'svelte/transition';
	import { ImagePlus, Trash2, X, ZoomIn } from 'lucide-svelte';
	import { api, type ScreenshotDto } from '$lib/api';
	import {
		appendScreenshot,
		closeTrade,
		removeTrade,
		requestClose,
		selectedTradeId,
		trades,
		updateScreenshot,
		upsertTrade
	} from '$lib/stores/trades';
	import { toasts } from '$lib/stores/toast';
	import { fmtDateTime, fmtMoney, fmtNum, fmtR, pnlTone, toneText } from '$lib/utils/format';
	import { DRAWER, FADE } from '$lib/utils/transitions';

	const LABELS = ['entry', 'exit', 'setup', 'mistake'] as const;

	const trade = $derived($selectedTradeId === null ? null : ($trades.find((t) => t.id === $selectedTradeId) ?? null));

	let thesis = $state('');
	let notes = $state('');
	let tagInput = $state('');
	let uploadLabel: (typeof LABELS)[number] = $state('entry');
	let uploading = $state(false);
	let dragOver = $state(false);
	let zoomShot: ScreenshotDto | null = $state(null);
	let confirmDelete = $state(false);
	let saving = $state(false);
	let savingEdits = $state(false);
	let lastTradeId: number | null = $state(null);

	// Editable trade legs (strings so empty = clear nullable field).
	let fSymbol = $state('');
	let fDirection = $state('buy');
	let fSize = $state('');
	let fEntry = $state('');
	let fInitSl = $state('');
	let fCurrSl = $state('');
	let fTp = $state('');
	let fExit = $state('');
	let fFees = $state('');

	const numStr = (v: number | null | undefined): string => (v === null || v === undefined ? '' : String(v));

	$effect(() => {
		if (trade && trade.id !== lastTradeId) {
			lastTradeId = trade.id;
			thesis = trade.thesis ?? '';
			notes = trade.review_notes ?? '';
			tagInput = trade.tags.map((t) => `${t.category === 'mistake' ? '!' : '#'}${t.name}`).join(' ');
			fSymbol = trade.symbol ?? '';
			fDirection = (trade.direction ?? 'buy').toLowerCase();
			fSize = numStr(trade.size);
			fEntry = numStr(trade.entry_price);
			fInitSl = numStr(trade.initial_sl);
			fCurrSl = numStr(trade.current_sl);
			fTp = numStr(trade.tp);
			fExit = numStr(trade.exit_price);
			fFees = numStr(trade.fees);
			confirmDelete = false;
			zoomShot = null;
		}
		if (!trade) lastTradeId = null;
	});

	const dirty = $derived(trade !== null && (thesis !== (trade.thesis ?? '') || notes !== (trade.review_notes ?? '')));
	const tagsDirty = $derived(
		trade !== null &&
			tagInput.trim() !== trade.tags.map((t) => `${t.category === 'mistake' ? '!' : '#'}${t.name}`).join(' ')
	);
	const editsDirty = $derived(
		trade !== null &&
			(fSymbol.trim().toUpperCase() !== (trade.symbol ?? '') ||
				fDirection !== (trade.direction ?? '').toLowerCase() ||
				fSize.trim() !== numStr(trade.size) ||
				fEntry.trim() !== numStr(trade.entry_price) ||
				fInitSl.trim() !== numStr(trade.initial_sl) ||
				fCurrSl.trim() !== numStr(trade.current_sl) ||
				fTp.trim() !== numStr(trade.tp) ||
				fExit.trim() !== numStr(trade.exit_price) ||
				fFees.trim() !== numStr(trade.fees))
	);

	function onBackdrop(e: MouseEvent): void {
		if (e.target === e.currentTarget) closeTrade();
	}

	function onBackdropKey(e: KeyboardEvent): void {
		if (e.key === 'Escape') {
			if (zoomShot) zoomShot = null;
			else closeTrade();
		}
	}

	function onZoomBackdrop(e: MouseEvent): void {
		if (e.target === e.currentTarget) zoomShot = null;
	}

	function onZoomBackdropKey(e: KeyboardEvent): void {
		if (e.key === 'Escape') zoomShot = null;
	}

	async function saveNotes(): Promise<void> {
		if (!trade || saving) return;
		saving = true;
		try {
			const updated = await api.patchTrade(trade.id, { thesis: thesis || null, review_notes: notes || null });
			upsertTrade(updated);
			toasts.push('success', 'Notes saved.');
		} catch (err) {
			toasts.push('error', `Save failed — ${err instanceof Error ? err.message : 'unknown error'}`);
		} finally {
			saving = false;
		}
	}

	async function saveTags(): Promise<void> {
		if (!trade || saving) return;
		saving = true;
		try {
			const tokens = tagInput.split(/[\s,]+/).filter(Boolean);
			const updated = await api.patchTrade(trade.id, { tags: tokens });
			upsertTrade(updated);
			toasts.push('success', 'Tags updated.');
		} catch (err) {
			toasts.push('error', `Tag update failed — ${err instanceof Error ? err.message : 'unknown error'}`);
		} finally {
			saving = false;
		}
	}

	async function saveEdits(): Promise<void> {
		if (!trade || savingEdits) return;
		const payload: Record<string, unknown> = {};
		if (fSymbol.trim().toUpperCase() !== (trade.symbol ?? '')) {
			if (!fSymbol.trim()) {
				toasts.push('error', 'Symbol cannot be empty.');
				return;
			}
			payload.symbol = fSymbol.trim().toUpperCase();
		}
		if (fDirection !== (trade.direction ?? '').toLowerCase()) {
			if (fDirection !== 'buy' && fDirection !== 'sell') {
				toasts.push('error', 'Direction must be buy or sell.');
				return;
			}
			payload.direction = fDirection;
		}
		const nums: [key: string, raw: string, current: number | null][] = [
			['size', fSize, trade.size],
			['entry_price', fEntry, trade.entry_price],
			['initial_sl', fInitSl, trade.initial_sl],
			['current_sl', fCurrSl, trade.current_sl],
			['tp', fTp, trade.tp],
			['exit_price', fExit, trade.exit_price],
			['fees', fFees, trade.fees]
		];
		for (const [key, raw, current] of nums) {
			const t = raw.trim();
			if (t === numStr(current)) continue;
			if (t === '') {
				payload[key] = null;
				continue;
			}
			const v = Number(t);
			if (!Number.isFinite(v)) {
				toasts.push('error', `Bad ${key.replace('_', ' ')}: ${t}`);
				return;
			}
			payload[key] = v;
		}
		if (Object.keys(payload).length === 0) return;
		savingEdits = true;
		try {
			const updated = await api.patchTrade(trade.id, payload);
			upsertTrade(updated);
			toasts.push('success', 'Trade updated — net and R recomputed.');
		} catch (err) {
			toasts.push('error', `Update failed — ${err instanceof Error ? err.message : 'unknown error'}`);
		} finally {
			savingEdits = false;
		}
	}

	async function changeShotLabel(tradeId: number, shot: ScreenshotDto, select: HTMLSelectElement): Promise<void> {
		if (select.value === shot.label) return;
		try {
			const updated = await api.patchScreenshot(shot.id, select.value);
			updateScreenshot(tradeId, updated);
			toasts.push('success', `Screenshot labeled ${updated.label}.`);
		} catch (err) {
			select.value = shot.label;
			toasts.push('error', `Label update failed — ${err instanceof Error ? err.message : 'unknown error'}`);
		}
	}

	async function uploadFiles(files: FileList | File[]): Promise<void> {
		if (!trade || uploading) return;
		const imgs = [...files].filter((f) => f.type.startsWith('image/'));
		if (imgs.length === 0) {
			toasts.push('error', 'Only image files can be uploaded.');
			return;
		}
		uploading = true;
		try {
			for (const file of imgs) {
				const shot = await api.uploadScreenshot(trade.id, file, uploadLabel);
				appendScreenshot(trade.id, shot);
			}
			toasts.push('success', `${imgs.length} screenshot${imgs.length === 1 ? '' : 's'} attached.`);
		} catch (err) {
			toasts.push('error', `Upload failed — ${err instanceof Error ? err.message : 'unknown error'}`);
		} finally {
			uploading = false;
		}
	}

	function onDrop(e: DragEvent): void {
		e.preventDefault();
		dragOver = false;
		if (e.dataTransfer?.files.length) void uploadFiles(e.dataTransfer.files);
	}

	function filesFromClipboard(e: ClipboardEvent): File[] {
		const cd = e.clipboardData;
		if (!cd) return [];
		if (cd.files?.length) return [...cd.files].filter((f) => f.type.startsWith('image/'));
		// Chrome/Snipping Tool often expose images via items with empty files.
		const out: File[] = [];
		for (const item of cd.items ?? []) {
			if (item.type.startsWith('image/')) {
				const f = item.getAsFile();
				if (f) out.push(f);
			}
		}
		return out;
	}

	function onPaste(e: ClipboardEvent): void {
		if (!trade || uploading) return;
		const imgs = filesFromClipboard(e);
		if (imgs.length) {
			e.preventDefault();
			void uploadFiles(imgs);
		}
	}

	async function doDelete(): Promise<void> {
		if (!trade) return;
		if (!confirmDelete) {
			confirmDelete = true;
			setTimeout(() => (confirmDelete = false), 4000);
			return;
		}
		try {
			await api.deleteTrade(trade.id);
			removeTrade(trade.id);
			toasts.push('success', 'Trade deleted.');
		} catch (err) {
			toasts.push('error', `Delete failed — ${err instanceof Error ? err.message : 'unknown error'}`);
		}
	}

	const METRICS = [
		{ label: 'Entry', get: (t: NonNullable<typeof trade>) => fmtNum(t.entry_price) },
		{ label: 'Exit', get: (t: NonNullable<typeof trade>) => fmtNum(t.exit_price) },
		{ label: 'Stop', get: (t: NonNullable<typeof trade>) => fmtNum(t.current_sl ?? t.initial_sl) },
		{ label: 'Target', get: (t: NonNullable<typeof trade>) => fmtNum(t.tp) },
		{ label: 'Size', get: (t: NonNullable<typeof trade>) => (t.size === null ? '—' : String(t.size)) },
		{ label: 'Fees', get: (t: NonNullable<typeof trade>) => fmtMoney(t.fees) }
	] as const;
</script>

<svelte:window onkeydown={onBackdropKey} onpaste={onPaste} />

{#if trade}
	<div
		transition:fade={FADE}
		onclick={onBackdrop}
		onkeydown={onBackdropKey}
		tabindex={-1}
		class="fixed inset-0 z-50 bg-base/75 backdrop-blur-[3px]"
		role="dialog"
		aria-modal="true"
		aria-label="Trade detail"
	>
		<div
			transition:fly={DRAWER}
			class="absolute inset-y-0 right-0 flex w-full max-w-md flex-col border-l border-line bg-panel shadow-pop"
		>
			<!-- Header -->
			<div class="flex shrink-0 items-center gap-2 border-b border-line px-5 py-4">
				<span class="num text-lg font-semibold text-fg uppercase">{trade.symbol ?? '—'}</span>
				<span
					class="rounded-lg px-2 py-0.5 font-mono text-[10px] font-semibold tracking-[0.14em] uppercase {(trade.direction ?? '').toLowerCase() ===
					'sell'
						? 'bg-loss/12 text-loss'
						: 'bg-win/12 text-win'}"
				>
					{trade.direction ?? '—'}
				</span>
				<span
					class="rounded-lg px-2 py-0.5 font-mono text-[10px] font-semibold tracking-[0.14em] uppercase {trade.status ===
					'OPEN'
						? 'bg-accent/12 text-accent'
						: 'bg-flat/12 text-flat'}"
				>
					{trade.status}
				</span>

				<span class="ml-auto flex shrink-0 items-center gap-2">
					{#if trade.status === 'OPEN'}
						<button type="button" onclick={() => requestClose(trade.id)} class="btn btn-danger h-8 px-3 text-[13px]">
							Close trade
						</button>
					{/if}
					<button
						type="button"
						onclick={closeTrade}
						aria-label="Close"
						class="btn-icon h-8 w-8"
					>
						<X size={17} strokeWidth={1.8} aria-hidden="true" />
					</button>
				</span>
			</div>

			<div class="no-scrollbar min-h-0 flex-1 overflow-y-auto px-5 py-5">
				<!-- Metrics -->
				<dl class="grid grid-cols-3 gap-x-4 gap-y-4 sm:grid-cols-3">
					{#each METRICS as m}
						<div class="min-w-0">
							<dt class="eyebrow">{m.label}</dt>
							<dd class="num mt-1 truncate text-sm text-fg">{m.get(trade)}</dd>
						</div>
					{/each}
					<div>
						<dt class="eyebrow">Net</dt>
						<dd class="num mt-1 text-sm font-semibold {toneText[pnlTone(trade.net_pnl)]}">
							{fmtMoney(trade.net_pnl)}
						</dd>
					</div>
					<div>
						<dt class="eyebrow">R</dt>
						<dd class="num mt-1 text-sm font-semibold {toneText[pnlTone(trade.r_multiple)]}">
							{fmtR(trade.r_multiple)}
						</dd>
					</div>
					<div class="min-w-0">
						<dt class="eyebrow">Ticket</dt>
						<dd class="num mt-1 truncate text-sm text-mut">{trade.trade_id}</dd>
					</div>
				</dl>
				<p class="num mt-4 border-t border-line pt-3 text-[11px] text-dim">
					Opened {fmtDateTime(trade.timestamp_open)}
					{#if trade.timestamp_close} · Closed {fmtDateTime(trade.timestamp_close)}{/if}
				</p>

				<!-- Trade details editor -->
				<div class="mt-5">
					<div class="mb-2 flex items-center justify-between">
						<span class="eyebrow">Trade details</span>
						<button
							type="button"
							onclick={() => void saveEdits()}
							disabled={!editsDirty || savingEdits}
							class="btn btn-ghost h-7 shrink-0 px-3 text-[12px]"
						>
							{savingEdits ? 'Saving…' : 'Save changes'}
						</button>
					</div>
					<div class="grid grid-cols-3 gap-2">
						<label class="flex min-w-0 flex-col gap-1">
							<span class="eyebrow">Symbol</span>
							<input type="text" bind:value={fSymbol} class="field h-9 font-mono text-[13px]" />
						</label>
						<label class="flex min-w-0 flex-col gap-1">
							<span class="eyebrow">Side</span>
							<select bind:value={fDirection} class="field h-9 font-mono text-[13px]">
								<option value="buy">buy</option>
								<option value="sell">sell</option>
							</select>
						</label>
						<label class="flex min-w-0 flex-col gap-1">
							<span class="eyebrow">Size</span>
							<input type="text" inputmode="decimal" bind:value={fSize} class="field h-9 font-mono text-[13px]" />
						</label>
						<label class="flex min-w-0 flex-col gap-1">
							<span class="eyebrow">Entry</span>
							<input type="text" inputmode="decimal" bind:value={fEntry} class="field h-9 font-mono text-[13px]" />
						</label>
						<label class="flex min-w-0 flex-col gap-1">
							<span class="eyebrow">Init SL</span>
							<input type="text" inputmode="decimal" bind:value={fInitSl} class="field h-9 font-mono text-[13px]" />
						</label>
						<label class="flex min-w-0 flex-col gap-1">
							<span class="eyebrow">Curr SL</span>
							<input type="text" inputmode="decimal" bind:value={fCurrSl} class="field h-9 font-mono text-[13px]" />
						</label>
						<label class="flex min-w-0 flex-col gap-1">
							<span class="eyebrow">Target</span>
							<input type="text" inputmode="decimal" bind:value={fTp} class="field h-9 font-mono text-[13px]" />
						</label>
						<label class="flex min-w-0 flex-col gap-1">
							<span class="eyebrow">Exit</span>
							<input type="text" inputmode="decimal" bind:value={fExit} class="field h-9 font-mono text-[13px]" />
						</label>
						<label class="flex min-w-0 flex-col gap-1">
							<span class="eyebrow">Fees</span>
							<input type="text" inputmode="decimal" bind:value={fFees} class="field h-9 font-mono text-[13px]" />
						</label>
					</div>
					<p class="num mt-1.5 text-[11px] text-dim">Net and R recompute automatically from prices and fees.</p>
				</div>

				<!-- Editors -->
				<div class="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2">
					<label class="flex flex-col gap-1.5">
						<span class="eyebrow">Thesis</span>
						<textarea
							bind:value={thesis}
							rows={4}
							placeholder="Why did you take this trade?"
							class="field resize-y text-[13px]"
						></textarea>
					</label>
					<label class="flex flex-col gap-1.5">
						<span class="eyebrow">Review notes</span>
						<textarea
							bind:value={notes}
							rows={4}
							placeholder="What worked, what didn't?"
							class="field resize-y text-[13px]"
						></textarea>
					</label>
				</div>
				<div class="mt-2 flex justify-end">
					<button
						type="button"
						onclick={() => void saveNotes()}
						disabled={!dirty || saving}
						class="btn btn-primary h-8 px-3.5 text-[13px]"
					>
						{saving ? 'Saving…' : 'Save notes'}
					</button>
				</div>

				<label class="mt-4 flex flex-col gap-1.5">
					<span class="eyebrow">Tags — <span class="normal-case text-mut">#setup !mistake</span></span>
					<span class="flex gap-2">
						<input
							type="text"
							bind:value={tagInput}
							placeholder="#fvg !early"
							class="field h-9 flex-1 font-mono text-[13px]"
						/>
						<button
							type="button"
							onclick={() => void saveTags()}
							disabled={!tagsDirty || saving}
							class="btn btn-ghost h-9 shrink-0 px-3.5 text-[13px]"
						>
							Apply
						</button>
					</span>
				</label>

				<!-- Upload zone -->
				<div class="mt-5">
					<div class="mb-2 flex items-center justify-between">
						<span class="eyebrow">Screenshots</span>
						<label class="flex items-center gap-1.5 font-mono text-[11px] tabular-nums text-dim">
							label
							<select
								bind:value={uploadLabel}
								class="rounded-lg border border-line bg-raised px-1.5 py-1 text-[11px] text-fg outline-none"
							>
								{#each LABELS as l}<option value={l}>{l}</option>{/each}
							</select>
						</label>
					</div>
					<div
						role="button"
						tabindex={0}
						aria-label="Upload screenshots"
						ondrop={onDrop}
						ondragover={(e) => {
							e.preventDefault();
							dragOver = true;
						}}
						ondragleave={() => (dragOver = false)}
						onpaste={onPaste}
						onkeydown={(e) => {
							if (e.key === 'Enter') document.getElementById('shot-file')?.click();
						}}
						class="flex cursor-pointer flex-col items-center gap-2 rounded-2xl border border-dashed px-6 py-7 text-center transition-all duration-200 {dragOver
							? 'border-accent/60 bg-accent/8 shadow-glow'
							: 'border-line hover:border-edge hover:bg-raised/40'}"
						onclick={() => document.getElementById('shot-file')?.click()}
					>
						<span
							class="grid h-10 w-10 place-items-center rounded-xl bg-accent/12 text-accent {dragOver
								? 'scale-110'
								: ''} transition-transform duration-300 ease-spring"
						>
							<ImagePlus size={19} strokeWidth={1.7} aria-hidden="true" />
						</span>
						<p class="text-[13px] leading-relaxed text-mut">
							{uploading ? 'Uploading…' : 'Drop images, paste from clipboard, or click to browse'}
						</p>
						<input
							id="shot-file"
							type="file"
							accept="image/*"
							multiple
							class="hidden"
							onchange={(e) => {
								const files = e.currentTarget.files;
								if (files?.length) void uploadFiles(files);
								e.currentTarget.value = '';
							}}
						/>
					</div>

					{#if trade.screenshots.length > 0}
						<div class="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
							{#each trade.screenshots as shot (shot.id)}
								<div class="flex min-w-0 flex-col gap-1">
									<button
										type="button"
										onclick={() => (zoomShot = shot)}
										class="group relative aspect-video overflow-hidden rounded-xl border border-line bg-raised focus-visible:outline-none"
									>
										<span class="skeleton absolute inset-0" aria-hidden="true"></span>
										<img
											src={api.thumbUrl(shot.immich_asset_id)}
											alt="{shot.label} screenshot"
											loading="lazy"
											onload={(e) => (e.currentTarget.previousElementSibling as HTMLElement)?.remove()}
											class="absolute inset-0 h-full w-full object-cover transition-transform duration-300 ease-spring group-hover:scale-[1.04]"
										/>
										<span
											class="absolute inset-0 bg-base/40 opacity-0 transition-opacity duration-200 group-hover:opacity-100"
											aria-hidden="true"
										></span>
										<ZoomIn
											size={15}
											strokeWidth={1.8}
											aria-hidden="true"
											class="absolute right-1.5 bottom-1.5 z-10 text-accent opacity-0 transition-opacity duration-200 group-hover:opacity-100"
										/>
									</button>
									<select
										value={shot.label}
										aria-label="Screenshot label"
										onchange={(e) => void changeShotLabel(trade.id, shot, e.currentTarget)}
										class="h-7 w-full rounded-lg border border-line bg-raised px-1.5 font-mono text-[11px] text-fg outline-none"
									>
										{#each LABELS as l}<option value={l}>{l}</option>{/each}
									</select>
								</div>
							{/each}
						</div>
					{/if}
				</div>

				<!-- Delete -->
				<div class="mt-6 flex justify-end border-t border-line pt-4">
					<button
						type="button"
						onclick={() => void doDelete()}
						class="btn h-8 gap-1.5 px-3 text-[13px] {confirmDelete
							? 'btn-danger shadow-pop'
							: 'text-loss hover:bg-loss/10'}"
					>
						<Trash2 size={14} strokeWidth={1.8} aria-hidden="true" />
						{confirmDelete ? 'Confirm delete?' : 'Delete trade'}
					</button>
				</div>
			</div>
		</div>
	</div>
{/if}

{#if zoomShot}
	<div
		transition:fade={FADE}
		class="fixed inset-0 z-[60] grid place-items-center bg-base/90 p-4 backdrop-blur-sm"
		role="dialog"
		tabindex={-1}
		aria-modal="true"
		aria-label="Screenshot zoom"
		onclick={onZoomBackdrop}
		onkeydown={onZoomBackdropKey}
	>
		<button
			type="button"
			onclick={() => (zoomShot = null)}
			aria-label="Close zoom"
			class="btn-icon absolute top-4 right-4 h-9 w-9 border-edge bg-raised/80 text-fg"
		>
			<X size={18} strokeWidth={1.8} aria-hidden="true" />
		</button>
		<img
			src={zoomShot ? api.fullUrl(zoomShot.immich_asset_id) : ''}
			alt="Full resolution screenshot"
			class="max-h-[90dvh] max-w-full rounded-xl object-contain shadow-pop"
		/>
	</div>
{/if}
