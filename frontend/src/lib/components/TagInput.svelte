<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { fly } from 'svelte/transition';
	import type { TagSummaryDto } from '$lib/api';
	import { tagOptions, loadTagOptions } from '$lib/stores/tags';

	type Mode = 'setup' | 'mistake' | 'both';
	type Prefix = '#' | '!';
	type Suggestion = { tag: TagSummaryDto; prefix: Prefix };
	type Group = {
		key: string;
		label: string;
		prefix: Prefix;
		items: Suggestion[];
		offset: number;
	};

	const MAX_PER_GROUP = 6;
	const uid = $props.id();

	let {
		value = $bindable(''),
		mode = 'both',
		placeholder = '',
		ariaLabel = 'Tags',
		inputClass = 'field font-mono text-[13px]',
		wrapperClass = '',
		onValueChange
	}: {
		value?: string;
		mode?: Mode;
		placeholder?: string;
		ariaLabel?: string;
		inputClass?: string;
		wrapperClass?: string;
		onValueChange?: () => void;
	} = $props();

	let inputEl: HTMLInputElement | null = $state(null);
	let open = $state(false);
	let active = $state(0);
	let typedPrefix = $state<Prefix | ''>('');
	let query = $state('');
	let tokenStart = $state(0);
	let tokenEnd = $state(0);

	onMount(() => {
		void loadTagOptions();
	});

	const listboxId = `${uid}-listbox`;

	function tokenBounds(text: string, caret: number): { start: number; end: number } {
		let start = Math.max(0, Math.min(caret, text.length));
		while (start > 0 && !/[\s,]/.test(text[start - 1])) start -= 1;
		let end = Math.max(0, Math.min(caret, text.length));
		while (end < text.length && !/[\s,]/.test(text[end])) end += 1;
		return { start, end };
	}

	function syncQuery(): void {
		const el = inputEl;
		if (!el) return;
		const caret = el.selectionStart ?? value.length;
		const bounds = tokenBounds(value, caret);
		const token = value.slice(bounds.start, caret);
		const prefix: Prefix | '' = token.startsWith('!') ? '!' : token.startsWith('#') ? '#' : '';
		tokenStart = bounds.start;
		tokenEnd = bounds.end;
		typedPrefix = prefix;
		query = (prefix ? token.slice(1) : token).toLowerCase();
		active = 0;
		open = true;
	}

	/** Rank exact starts-with matches ahead of anything that merely contains it. */
	function ranked(tags: TagSummaryDto[]): TagSummaryDto[] {
		const starts = tags.filter((t) => t.name.startsWith(query));
		const contains = tags.filter((t) => !t.name.startsWith(query) && t.name.includes(query));
		const byUse = (a: TagSummaryDto, b: TagSummaryDto): number =>
			b.trade_count - a.trade_count || a.name.localeCompare(b.name);
		starts.sort(byUse);
		contains.sort(byUse);
		return [...starts, ...contains].slice(0, MAX_PER_GROUP);
	}

	const categories = $derived.by((): Array<'setup' | 'mistake'> => {
		if (mode === 'setup') return typedPrefix === '!' ? [] : ['setup'];
		if (mode === 'mistake') return typedPrefix === '#' ? [] : ['mistake'];
		if (typedPrefix === '!') return ['mistake'];
		if (typedPrefix === '#') return ['setup'];
		return ['setup', 'mistake'];
	});

	const groups = $derived.by((): Group[] => {
		const result: Group[] = [];
		let offset = 0;
		for (const category of categories) {
			const prefix: Prefix = category === 'mistake' ? '!' : '#';
			const matches = ranked($tagOptions.filter((tag) => tag.category === category));
			if (matches.length === 0) continue;
			const items = matches.map((tag) => ({ tag, prefix }));
			result.push({
				key: category,
				label: category === 'mistake' ? 'Mistakes' : 'Setups',
				prefix,
				items,
				offset
			});
			offset += items.length;
		}
		return result;
	});

	const flat = $derived(groups.flatMap((group) => group.items));

	const wrongPrefix = $derived(
		(mode === 'setup' && typedPrefix === '!') || (mode === 'mistake' && typedPrefix === '#')
	);

	const hint = $derived.by((): string | null => {
		if (wrongPrefix) {
			return mode === 'setup' ? 'Use # for a setup tag.' : 'Use ! for a mistake tag.';
		}
		if (query.length > 0 && flat.length === 0) {
			return `No matching tag — “${typedPrefix}${query}” will be created when you save.`;
		}
		return null;
	});

	const expanded = $derived(open && (flat.length > 0 || hint !== null));
	const activeSuggestion = $derived(flat[active] ?? null);

	function handleInput(event: Event): void {
		value = (event.currentTarget as HTMLInputElement).value;
		syncQuery();
		onValueChange?.();
	}

	function handleFocus(): void {
		syncQuery();
	}

	function handleClick(): void {
		syncQuery();
	}

	function handleBlur(): void {
		// A click on an option fires mousedown before blur; the small delay
		// lets that click land before the menu is removed from the DOM.
		window.setTimeout(() => {
			open = false;
		}, 120);
	}

	async function choose(item: Suggestion): Promise<void> {
		const prefix: Prefix = mode === 'setup' ? '#' : mode === 'mistake' ? '!' : item.prefix;
		const replacement = `${prefix}${item.tag.name}`;
		const before = value.slice(0, tokenStart);
		const after = value.slice(tokenEnd).replace(/^[\s,]+/, '');
		const next = `${before}${replacement}${after ? ` ${after}` : ' '}`;
		value = next;
		onValueChange?.();
		open = false;
		await tick();
		inputEl?.focus();
		const caret = before.length + replacement.length + 1;
		inputEl?.setSelectionRange(caret, caret);
	}

	function handleKeydown(event: KeyboardEvent): void {
		if (event.key === 'ArrowDown') {
			event.preventDefault();
			if (!open) syncQuery();
			if (flat.length > 0) active = (active + 1) % flat.length;
			return;
		}
		if (event.key === 'ArrowUp') {
			event.preventDefault();
			if (!open) syncQuery();
			if (flat.length > 0) active = (active - 1 + flat.length) % flat.length;
			return;
		}
		if (event.key === 'Escape') {
			if (open) {
				event.preventDefault();
				open = false;
			}
			return;
		}
		if ((event.key === 'Enter' || event.key === 'Tab') && activeSuggestion) {
			event.preventDefault();
			event.stopPropagation();
			void choose(activeSuggestion);
		}
	}

	function optionId(index: number): string {
		return `${uid}-option-${index}`;
	}
</script>

<div class="relative {wrapperClass}">
	<input
		bind:this={inputEl}
		value={value}
		oninput={handleInput}
		onfocus={handleFocus}
		onclick={handleClick}
		onblur={handleBlur}
		onkeydown={handleKeydown}
		type="text"
		{placeholder}
		autocomplete="off"
		autocapitalize="off"
		spellcheck="false"
		class={inputClass}
		role="combobox"
		aria-autocomplete="list"
		aria-haspopup="listbox"
		aria-expanded={expanded}
		aria-controls={listboxId}
		aria-activedescendant={expanded && activeSuggestion ? optionId(active) : undefined}
		aria-label={ariaLabel}
	/>

	{#if expanded}
		<div
			id={listboxId}
			role="listbox"
			aria-label="Tag suggestions"
			transition:fly={{ y: -4, duration: 120 }}
			class="absolute left-0 right-0 top-full z-50 mt-1.5 max-h-64 overflow-y-auto rounded-xl border border-line bg-panel p-1 shadow-pop"
		>
			{#each groups as group (group.key)}
				<div class="mb-1">
					<div class="eyebrow px-2 pb-1 pt-1.5">{group.label}</div>
					{#each group.items as item, index (item.tag.id)}
						{@const itemIndex = group.offset + index}
						<button
							type="button"
							role="option"
							id={optionId(itemIndex)}
							aria-selected={active === itemIndex}
							onmouseenter={() => (active = itemIndex)}
							onmousedown={(event) => event.preventDefault()}
							onclick={() => void choose(item)}
							class="flex w-full items-center gap-1.5 rounded-lg px-2 py-1.5 text-left transition-colors {active === itemIndex
								? 'bg-raised text-fg'
								: 'text-mut hover:bg-raised/60 hover:text-fg'}"
						>
							<span class="num text-[11px] font-semibold {group.prefix === '!' ? 'text-loss' : 'text-win'}">{group.prefix}</span>
							<span class="min-w-0 flex-1 truncate text-[13px]">{item.tag.name}</span>
							{#if item.tag.trade_count > 0}
								<span class="num text-[10.5px] text-dim">{item.tag.trade_count}</span>
							{/if}
						</button>
					{/each}
				</div>
			{/each}
			{#if hint}
				<p class="px-2 py-2 text-[11.5px] leading-snug text-dim">{hint}</p>
			{/if}
		</div>
	{/if}
</div>
