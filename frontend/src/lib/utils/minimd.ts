/** Minimal markdown renderer for LLM summaries — no dependency, XSS-safe.
 *
 * The review prompt constrains output to headings / bold / bullet lists,
 * so this supports exactly that subset — plus a graceful table fallback
 * (prompt forbids tables, but they render sanely if one slips through).
 * Raw HTML is escaped first, so {@html} stays safe even when the model
 * echoes note text verbatim.
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
	const isDelim = (line: string): boolean => /^\|?[\s:|-]+\|?[\s:|-]*$/.test(line) && line.includes('|');
	const splitRow = (line: string): string[] => {
		let cells = line.trim().split('|').map((c) => c.trim());
		if (cells.length > 0 && cells[0] === '') cells = cells.slice(1);
		if (cells.length > 0 && cells[cells.length - 1] === '') cells = cells.slice(0, -1);
		return cells;
	};
	for (let i = 0; i < lines.length; i++) {
		const line = lines[i].trim();
		if (!line) {
			closeList();
			continue;
		}
		// Markdown table fallback (prompt forbids these, but render gracefully if one slips through).
		if (line.includes('|') && i + 1 < lines.length && isDelim(lines[i + 1].trim())) {
			closeList();
			const head = splitRow(line);
			const body: string[][] = [];
			i += 2;
			while (i < lines.length && lines[i].trim().includes('|')) {
				body.push(splitRow(lines[i]));
				i++;
			}
			i--;
			const cell = 'px-2 py-1.5 text-left align-top text-[12.5px] leading-relaxed text-mut';
			html.push('<div class="mt-2 overflow-x-auto rounded-lg border border-line">');
			html.push('<table class="w-full min-w-[520px] border-collapse">');
			html.push(
				`<thead><tr class="border-b border-line bg-raised/60">${head.map((c) => `<th class="${cell} font-mono text-[10px] tracking-[0.12em] text-dim uppercase">${inline(c)}</th>`).join('')}</tr></thead>`
			);
			html.push(
				`<tbody>${body.map((row) => `<tr class="border-b border-line last:border-0">${row.map((c) => `<td class="${cell}">${inline(c)}</td>`).join('')}</tr>`).join('')}</tbody>`
			);
			html.push('</table></div>');
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
		const dotBullet = line.match(/^•\s*(.*)/);
		if (bullet || ordered || dotBullet) {
			if (!listOpen) {
				html.push('<ul class="mt-2 flex flex-col gap-1.5">');
				listOpen = true;
			}
			html.push(
				`<li class="flex gap-2 text-[13px] leading-relaxed text-mut"><span aria-hidden="true" class="text-accent">•</span><span>${inline((bullet ?? ordered ?? dotBullet)![1])}</span></li>`
			);
			continue;
		}
		closeList();
		html.push(`<p class="mt-2 text-[13px] leading-relaxed text-mut first:mt-0">${inline(line)}</p>`);
	}
	closeList();
	return html.join('');
}
