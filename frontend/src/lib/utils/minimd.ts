/** Minimal markdown renderer for LLM summaries — no dependency, XSS-safe.
 *
 * The review prompt constrains output to headings / bold / bullet lists,
 * so this supports exactly that subset. Raw HTML is escaped first, so
 * {@html} stays safe even when the model echoes note text verbatim.
 */

function escapeHtml(src: string): string {
	return src
		.replace(/&/g, '&amp;')
		.replace(/</g, '&lt;')
		.replace(/>/g, '&gt;')
		.replace(/"/g, '&quot;');
}

function inline(src: string): string {
	return escapeHtml(src).replace(/\*\*(.+?)\*\*/g, '<strong class="font-semibold text-fg">$1</strong>');
}

export function renderMiniMarkdown(md: string): string {
	const lines = (md ?? '').split('\n');
	const html: string[] = [];
	let listOpen = false;
	const closeList = (): void => {
		if (listOpen) {
			html.push('</ul>');
			listOpen = false;
		}
	};
	for (const raw of lines) {
		const line = raw.trim();
		if (!line) {
			closeList();
			continue;
		}
		const h3 = line.match(/^###\s+(.*)/);
		const h2 = line.match(/^##\s+(.*)/);
		const h1 = line.match(/^#\s+(.*)/);
		if (h3 || h2 || h1) {
			closeList();
			const text = (h3 ?? h2 ?? h1)![1];
			const cls = h3
				? 'mt-4 text-[13px] font-semibold tracking-wide text-fg uppercase first:mt-0'
				: 'mt-4 text-base font-semibold text-fg first:mt-0';
			html.push(`<h4 class="${cls}">${inline(text)}</h4>`);
			continue;
		}
		const bullet = line.match(/^[-*]\s+(.*)/);
		const ordered = line.match(/^\d+[.)]\s+(.*)/);
		if (bullet || ordered) {
			if (!listOpen) {
				html.push('<ul class="mt-2 flex flex-col gap-1.5">');
				listOpen = true;
			}
			html.push(
				`<li class="flex gap-2 text-[13px] leading-relaxed text-mut"><span aria-hidden="true" class="text-accent">•</span><span>${inline((bullet ?? ordered)![1])}</span></li>`
			);
			continue;
		}
		closeList();
		html.push(`<p class="mt-2 text-[13px] leading-relaxed text-mut first:mt-0">${inline(line)}</p>`);
	}
	closeList();
	return html.join('');
}
