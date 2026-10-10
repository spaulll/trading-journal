/** Number / date formatting helpers. All figures use tabular numerals. */

/** Display timezone — every clock in the UI renders in IST. Storage stays naive-UTC. */
export const DISPLAY_TZ = 'Asia/Kolkata';

const axisDayFmt = new Intl.DateTimeFormat('en-GB', {
	timeZone: DISPLAY_TZ,
	day: '2-digit',
	month: '2-digit'
});

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
	const d = v ? parseStoredUTC(v) : null;
	if (!d) return '—';
	return (
		d.toLocaleString('en-GB', {
			timeZone: DISPLAY_TZ,
			day: '2-digit',
			month: 'short',
			hour: '2-digit',
			minute: '2-digit',
			hour12: true
		}) + ' IST'
	);
}

export function fmtDate(v: string | null | undefined): string {
	const d = v ? parseStoredUTC(v) : null;
	if (!d) return '—';
	return d.toLocaleDateString('en-GB', {
		timeZone: DISPLAY_TZ,
		day: '2-digit',
		month: 'short',
		year: 'numeric'
	});
}

/**
 * Stored timestamps are naive UTC — parse them as UTC, never browser-local,
 * so a trader in any timezone sees the same instant.
 */
export function parseStoredUTC(v: string): Date | null {
	const s = v.trim();
	if (!s) return null;
	if (/^\d{4}-\d{2}-\d{2}$/.test(s)) {
		const d = new Date(`${s}T00:00:00Z`);
		return Number.isNaN(d.getTime()) ? null : d;
	}
	const d = new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(s) ? s : `${s}Z`);
	return Number.isNaN(d.getTime()) ? null : d;
}

/** UTC calendar-day key (`YYYY-MM-DD`) of a stored timestamp — matches backend day buckets. */
export function dayKeyOf(iso: string | null | undefined): string {
	if (!iso) return '';
	const d = parseStoredUTC(iso);
	if (!d) return '';
	return d.toISOString().slice(0, 10);
}

/** Epoch ms for chart axes from a stored timestamp. */
export function storedMs(v: string): number | null {
	const d = parseStoredUTC(v);
	return d ? d.getTime() : null;
}

/** uPlot x-axis tick (epoch ms) → DD/MM in IST. */
export function fmtAxisDay(ms: number): string {
	return axisDayFmt.format(new Date(ms));
}

/** Live `datetime-local` (UTC) → IST label for input previews; '' when invalid. */
export function previewIST(raw: string): string {
	const t = raw.trim();
	if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(t)) return '';
	return fmtDateTime(`${t}:00`);
}

const MT5_INPUT_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/;

/** MT5 wall `datetime-local` → UTC `YYYY-MM-DDTHH:MM:SS` (null when invalid). */
export function mt5WallToUTC(raw: string, offsetMinutes: number): string | null {
	const t = raw.trim();
	if (!MT5_INPUT_RE.test(t)) return null;
	const ms = Date.parse(`${t}:00Z`);
	if (Number.isNaN(ms)) return null;
	return new Date(ms - offsetMinutes * 60000).toISOString().slice(0, 19);
}

/** Stored UTC timestamp → MT5 wall `datetime-local` value ('' when missing). */
export function utcToMT5Wall(iso: string | null | undefined, offsetMinutes: number): string {
	if (!iso) return '';
	const d = parseStoredUTC(iso);
	if (!d) return '';
	return new Date(d.getTime() + offsetMinutes * 60000).toISOString().slice(0, 16);
}

/** Live MT5 `datetime-local` → IST label for input previews; '' when invalid. */
export function previewMT5(raw: string, offsetMinutes: number): string {
	const utc = mt5WallToUTC(raw, offsetMinutes);
	return utc ? fmtDateTime(utc) : '';
}

/** Duration in minutes → "4h 12m" / "38m". */
export function fmtDuration(min: number | null | undefined): string {
	if (min === null || min === undefined) return '—';
	if (min < 60) return `${Math.round(min)}m`;
	const h = Math.floor(min / 60);
	const m = Math.round(min % 60);
	return m ? `${h}h ${m}m` : `${h}h`;
}

/** Shared breakeven tolerance ($): |net_pnl| <= BE_TOL is breakeven. Mirrors backend BE_TOLERANCE. */
export const BE_TOL = 5.0;

/** Win = jade, loss = coral, breakeven/missing = neutral (theme-aware tokens).
 * Money P&L uses the $5 BE band; R multiples use plain sign (see rTone). */
export function pnlTone(v: number | null | undefined): 'win' | 'loss' | 'be' {
	if (v === null || v === undefined || Math.abs(v) <= BE_TOL) return 'be';
	return v > 0 ? 'win' : 'loss';
}

/** Sign-based tone for R multiples (no dollar BE band). */
export function rTone(v: number | null | undefined): 'win' | 'loss' | 'be' {
	if (v === null || v === undefined || v === 0) return 'be';
	return v > 0 ? 'win' : 'loss';
}

export const toneText: Record<'win' | 'loss' | 'be', string> = {
	win: 'text-win',
	loss: 'text-loss',
	be: 'text-flat'
};

/** Soft tinted background for P&L chips and calendar cells. */
export const toneBg: Record<'win' | 'loss' | 'be', string> = {
	win: 'bg-win/12',
	loss: 'bg-loss/12',
	be: 'bg-flat/12'
};
