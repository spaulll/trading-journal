<script lang="ts">
	import { fade, scale } from 'svelte/transition';
	import { ImagePlus, Trash2, X, ZoomIn } from 'lucide-svelte';
	import { api, type ScreenshotDto } from '$lib/api';
	import {
		appendScreenshot,
		closeTrade,
		removeTrade,
		selectedTradeId,
		trades,
		upsertTrade
	} from '$lib/stores/trades';
	import { toasts } from '$lib/stores/toast';
	import { fmtDateTime, fmtMoney, fmtNum, fmtR, pnlTone, toneText } from '$lib/utils/format';
	import { FADE, MODAL } from '$lib/utils/transitions';

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
	let lastTradeId: number | null = $state(null);

	$effect(() => {
		if (trade && trade.id !== lastTradeId) {
			lastTradeId = trade.id;
			thesis = trade.thesis ?? '';
			notes = trade.review_notes ?? '';
			tagInput = trade.tags.map((t) => `${t.category === 'mistake' ? '!' : '#'}${t.name}`).join(' ');
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

	function onPaste(e: ClipboardEvent): void {
		const files = e.clipboardData?.files;
		if (files?.length) void uploadFiles(files);
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
</script>

<svelte:window onkeydown={onBackdropKey} />

{#if trade}
	<div
		transition:fade={FADE}
		onclick={onBackdrop}
		onkeydown={onBackdropKey}
		tabindex={-1}
		class="fixed inset-0 z-50 overflow-y-auto bg-black/60 p-4 backdrop-blur-sm sm:p-6"
		role="dialog"
		aria-modal="true"
		aria-label="Trade detail"
	>
		<div
			transition:scale={MODAL}
			class="mx-auto w-full max-w-3xl rounded-2xl border border-slate-200 bg-white shadow-2xl dark:border-slate-800 dark:bg-surface-900"
		>
			<!-- Header -->
			<div class="flex items-center gap-3 border-b border-slate-200 px-5 py-4 dark:border-slate-800">
				<span class="font-mono text-base font-semibold uppercase">{trade.symbol ?? '—'}</span>
				<span
					class="rounded-full px-2 py-0.5 font-mono text-[11px] font-medium uppercase {(trade.direction ?? '').toLowerCase() === 'sell'
						? 'bg-rose-500/10 text-rose-600 dark:text-rose-400'
						: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'}"
				>
					{trade.direction ?? '—'}
				</span>
				<span
					class="rounded-full px-2 py-0.5 font-mono text-[11px] uppercase {trade.status === 'OPEN'
						? 'bg-sky-500/10 text-sky-600 dark:text-sky-400'
						: 'bg-slate-500/10 text-slate-500 dark:text-slate-400'}"
				>
					{trade.status}
				</span>
				<button
					type="button"
					onclick={closeTrade}
					aria-label="Close"
					class="ml-auto grid h-8 w-8 place-items-center rounded-lg text-slate-400 transition-all hover:bg-slate-100 hover:text-slate-700 active:scale-95 dark:hover:bg-surface-800 dark:hover:text-slate-200"
				>
					<X size={17} />
				</button>
			</div>

			<div class="max-h-[calc(100dvh-12rem)] overflow-y-auto px-5 py-4">
				<!-- Metrics -->
				<dl class="grid grid-cols-2 gap-x-4 gap-y-3 font-mono text-sm tabular-nums sm:grid-cols-4">
					<div><dt class="text-[11px] text-slate-400 uppercase">Entry</dt><dd>{fmtNum(trade.entry_price)}</dd></div>
					<div><dt class="text-[11px] text-slate-400 uppercase">Exit</dt><dd>{fmtNum(trade.exit_price)}</dd></div>
					<div><dt class="text-[11px] text-slate-400 uppercase">Stop</dt><dd>{fmtNum(trade.current_sl ?? trade.initial_sl)}</dd></div>
					<div><dt class="text-[11px] text-slate-400 uppercase">TP</dt><dd>{fmtNum(trade.tp)}</dd></div>
					<div><dt class="text-[11px] text-slate-400 uppercase">Size</dt><dd>{trade.size ?? '—'}</dd></div>
					<div><dt class="text-[11px] text-slate-400 uppercase">Fees</dt><dd>{fmtMoney(trade.fees)}</dd></div>
					<div>
						<dt class="text-[11px] text-slate-400 uppercase">Net</dt>
						<dd class="font-medium {toneText[pnlTone(trade.net_pnl)]}">{fmtMoney(trade.net_pnl)}</dd>
					</div>
					<div>
						<dt class="text-[11px] text-slate-400 uppercase">R</dt>
						<dd class="font-medium {toneText[pnlTone(trade.r_multiple)]}">{fmtR(trade.r_multiple)}</dd>
					</div>
				</dl>
				<p class="mt-3 font-mono text-[11px] text-slate-400 tabular-nums">
					Opened {fmtDateTime(trade.timestamp_open)}
					{#if trade.timestamp_close} · Closed {fmtDateTime(trade.timestamp_close)}{/if}
					· <span class="opacity-80">{trade.trade_id}</span>
				</p>

				<!-- Editors -->
				<div class="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2">
					<label class="flex flex-col gap-1.5">
						<span class="text-xs font-medium text-slate-500 dark:text-slate-400">Thesis</span>
						<textarea
							bind:value={thesis}
							rows={4}
							placeholder="Why did you take this trade?"
							class="resize-y rounded-lg border border-slate-200 bg-transparent p-2.5 text-sm outline-none placeholder:text-slate-400 focus:border-emerald-500 dark:border-slate-700"
						></textarea>
					</label>
					<label class="flex flex-col gap-1.5">
						<span class="text-xs font-medium text-slate-500 dark:text-slate-400">Review notes</span>
						<textarea
							bind:value={notes}
							rows={4}
							placeholder="What worked, what didn't?"
							class="resize-y rounded-lg border border-slate-200 bg-transparent p-2.5 text-sm outline-none placeholder:text-slate-400 focus:border-emerald-500 dark:border-slate-700"
						></textarea>
					</label>
				</div>
				<div class="mt-2 flex justify-end">
					<button
						type="button"
						onclick={() => void saveNotes()}
						disabled={!dirty || saving}
						class="h-8 rounded-lg bg-emerald-500 px-3.5 text-[13px] font-medium text-white transition-all duration-150 hover:bg-emerald-600 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-40"
					>
						{saving ? 'Saving…' : 'Save notes'}
					</button>
				</div>

				<label class="mt-3 flex flex-col gap-1.5">
					<span class="text-xs font-medium text-slate-500 dark:text-slate-400">Tags — <span class="font-mono">#setup !mistake</span></span>
					<span class="flex gap-2">
						<input
							type="text"
							bind:value={tagInput}
							placeholder="#fvg !early"
							class="h-9 flex-1 rounded-lg border border-slate-200 bg-transparent px-2.5 font-mono text-sm outline-none placeholder:text-slate-400 focus:border-emerald-500 dark:border-slate-700"
						/>
						<button
							type="button"
							onclick={() => void saveTags()}
							disabled={!tagsDirty || saving}
							class="h-9 shrink-0 rounded-lg border border-slate-200 px-3.5 text-[13px] font-medium transition-all duration-150 hover:border-emerald-500 hover:text-emerald-600 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-40 dark:border-slate-700 dark:hover:text-emerald-400"
						>
							Apply
						</button>
					</span>
				</label>

				<!-- Upload zone -->
				<div class="mt-5">
					<div class="mb-2 flex items-center justify-between">
						<span class="text-xs font-medium text-slate-500 dark:text-slate-400">Screenshots</span>
						<label class="flex items-center gap-1.5 font-mono text-[11px] text-slate-400">
							label
							<select
								bind:value={uploadLabel}
								class="rounded-md border border-slate-200 bg-transparent px-1.5 py-1 outline-none dark:border-slate-700 dark:bg-surface-900"
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
						class="flex cursor-pointer flex-col items-center gap-1.5 rounded-xl border border-dashed px-6 py-7 text-center transition-colors duration-150 {dragOver
							? 'border-emerald-500 bg-emerald-500/5'
							: 'border-slate-300 hover:border-slate-400 dark:border-slate-700 dark:hover:border-slate-500'}"
						onclick={() => document.getElementById('shot-file')?.click()}
					>
						<ImagePlus size={20} class="text-slate-400" />
						<p class="text-sm text-slate-500 dark:text-slate-400">
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
								<button
									type="button"
									onclick={() => (zoomShot = shot)}
									class="group relative aspect-video overflow-hidden rounded-lg border border-slate-200 bg-slate-100 dark:border-slate-800 dark:bg-surface-800"
								>
									<span class="absolute inset-0 animate-pulse bg-gradient-to-r from-slate-200 via-slate-100 to-slate-200 dark:from-surface-800 dark:via-surface-700 dark:to-surface-800"></span>
									<img
										src={api.thumbUrl(shot.immich_asset_id)}
										alt="{shot.label} screenshot"
										loading="lazy"
										onload={(e) => (e.currentTarget.previousElementSibling as HTMLElement)?.remove()}
										class="absolute inset-0 h-full w-full object-cover transition-transform duration-200 group-hover:scale-[1.03]"
									/>
									<span class="absolute bottom-1.5 left-1.5 rounded bg-black/60 px-1.5 py-0.5 font-mono text-[10px] text-white">
										{shot.label}
									</span>
									<ZoomIn size={15} class="absolute right-1.5 bottom-1.5 text-white opacity-0 drop-shadow transition-opacity group-hover:opacity-100" />
								</button>
							{/each}
						</div>
					{/if}
				</div>

				<!-- Delete -->
				<div class="mt-6 flex justify-end border-t border-slate-200 pt-4 dark:border-slate-800">
					<button
						type="button"
						onclick={() => void doDelete()}
						class="flex h-8 items-center gap-1.5 rounded-lg px-3 text-[13px] font-medium transition-all duration-150 active:scale-[0.98] {confirmDelete
							? 'bg-rose-500 text-white hover:bg-rose-600'
							: 'text-rose-600 hover:bg-rose-500/10 dark:text-rose-400'}"
					>
						<Trash2 size={14} />
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
		class="fixed inset-0 z-[60] grid place-items-center bg-black/85 p-4 backdrop-blur-sm"
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
			class="absolute top-4 right-4 grid h-9 w-9 place-items-center rounded-full bg-white/10 text-white transition-all hover:bg-white/20 active:scale-95"
		>
			<X size={18} />
		</button>
		<img
			src={zoomShot ? api.fullUrl(zoomShot.immich_asset_id) : ''}
			alt="Full resolution screenshot"
			class="max-h-[90dvh] max-w-full rounded-lg object-contain shadow-2xl"
		/>
	</div>
{/if}
