/** Number / date formatting helpers. All figures use tabular numerals. */

const money = new Intl.NumberFormat('en-US', {
	style: 'currency',
	currency: 'USD',
	minimumFractionDigits: 2,
	maximumFractionDigits: 2
});

export function fmtMoney(v: number | null | undefined): string {
	if (v === null || v === undefined) return '—';
	const sign = v > 0 ? '+' : '';
	return sign + money.format(v);
}

export function fmtR(v: number | null | undefined): string {
	if (v === null || v === undefined) return '—';
	const sign = v > 0 ? '+' : '';
	return `${sign}${v.toFixed(2)}R`;
}

export function fmtNum(v: number | null | undefined, digits = 2): string {
	if (v === null || v === undefined) return '—';
	return v.toFixed(digits);
}

export function fmtDateTime(v: string | null | undefined): string {
	if (!v) return '—';
	const d = new Date(v);
	if (Number.isNaN(d.getTime())) return '—';
	return d.toLocaleString('en-GB', {
		day: '2-digit',
		month: 'short',
		hour: '2-digit',
		minute: '2-digit'
	});
}

export function fmtDate(v: string | null | undefined): string {
	if (!v) return '—';
	const d = new Date(v);
	if (Number.isNaN(d.getTime())) return '—';
	return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

/** Emerald for winners, rose for losers, slate for breakeven/missing. */
export function pnlTone(v: number | null | undefined): 'win' | 'loss' | 'be' {
	if (v === null || v === undefined || v === 0) return 'be';
	return v > 0 ? 'win' : 'loss';
}

export const toneText: Record<'win' | 'loss' | 'be', string> = {
	win: 'text-accent-win',
	loss: 'text-accent-loss',
	be: 'text-accent-be'
};
