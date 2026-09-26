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

/** Compact form for hero statistics: $21.6k / -$1.9k. */
export function fmtMoneyShort(v: number | null | undefined): string {
	if (v === null || v === undefined) return '—';
	const abs = Math.abs(v);
	const body =
		abs >= 1000 ? `${(abs / 1000).toFixed(abs >= 10000 ? 1 : 2)}k` : abs.toFixed(0);
	const sign = v > 0 ? '+' : v < 0 ? '-' : '';
	return `${sign}$${body}`;
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

/** Duration in minutes → "4h 12m" / "38m". */
export function fmtDuration(min: number | null | undefined): string {
	if (min === null || min === undefined) return '—';
	if (min < 60) return `${Math.round(min)}m`;
	const h = Math.floor(min / 60);
	const m = Math.round(min % 60);
	return m ? `${h}h ${m}m` : `${h}h`;
}

/** Win = jade, loss = coral, breakeven/missing = neutral (theme-aware tokens). */
export function pnlTone(v: number | null | undefined): 'win' | 'loss' | 'be' {
	if (v === null || v === undefined || v === 0) return 'be';
	return v > 0 ? 'win' : 'loss';
}

export const toneText: Record<'win' | 'loss' | 'be', string> = {
	win: 'text-win',
	loss: 'text-loss',
	be: 'text-dim'
};

/** Soft tinted background for P&L chips and calendar cells. */
export const toneBg: Record<'win' | 'loss' | 'be', string> = {
	win: 'bg-win/12',
	loss: 'bg-loss/12',
	be: 'bg-flat/12'
};
