import { env } from '$env/dynamic/public';

/** Backend base URL. Override per environment with PUBLIC_API_BASE. */
export const API_BASE: string = env.PUBLIC_API_BASE ?? 'http://127.0.0.1:9000';

export interface TagDto {
	id: number;
	name: string;
	category: string;
}

export interface ScreenshotDto {
	id: number;
	trade_id: number;
	immich_asset_id: string;
	label: string;
	created_at: string;
}

export interface TradeDto {
	id: number;
	ticket: string;
	trade_id: string; // deprecated v1 alias of ticket — remove in Phase 5
	account_id: number | null;
	timestamp_open: string | null;
	timestamp_close: string | null;
	entry_time: string | null;
	exit_time: string | null;
	duration_minutes: number | null;
	session: string | null;
	direction: string | null;
	symbol: string | null;
	size: number | null;
	entry_price: number | null;
	initial_sl: number | null;
	current_sl: number | null;
	tp: number | null;
	exit_price: number | null;
	gross_pnl: number | null;
	fees: number | null;
	net_pnl: number | null;
	r_multiple: number | null;
	status: string;
	thesis: string | null;
	review_notes: string | null;
	created_at: string;
	updated_at: string;
	tags: TagDto[];
	screenshots: ScreenshotDto[];
}

export interface DailyNoteDto {
	id: number;
	date: string;
	pre_market: string | null;
	eod_review: string | null;
	discipline_breach: boolean;
	created_at: string;
	updated_at: string;
}

export interface AccountDto {
	id: number;
	firm: string;
	alias: string;
	login: string | null;
	phase: string;
	start_balance: number;
	daily_loss_pct: number;
	daily_basis: string;
	max_loss_pct: number;
	max_mode: string;
	trailing_ref: string;
	profit_target_pct: number | null;
	status: string;
	created_at: string;
	updated_at: string;
	open_trades: number;
	total_trades: number;
}

export interface PropStatusDto {
	account_id: number;
	alias: string;
	balance: number;
	total_net: number;
	daily_pnl: number;
	daily_loss_pct: number;
	daily_loss_limit: number;
	daily_left: number | null;
	daily_basis: string;
	max_loss_pct: number;
	max_loss_limit: number;
	max_mode: string;
	max_floor: number | null;
	max_left: number | null;
	profit_target_pct: number | null;
	profit_target: number | null;
	target_pct: number | null;
	breached: boolean;
	status: string;
	open_trades: number;
	total_trades: number;
}

export interface PagedTrades {
	items: TradeDto[];
	total: number;
	page: number;
	page_size: number;
}

export interface SyncResult {
	inserted: number;
	updated: number;
	total: number;
}

export interface SummaryDto {
	total_trades: number;
	open_trades: number;
	wins: number;
	losses: number;
	breakeven: number;
	net_pnl: number;
	win_rate: number;
	profit_factor: number | null;
	expectancy: number;
	avg_win: number;
	avg_loss: number;
	max_drawdown: number;
}

export interface EquityPoint {
	timestamp: string;
	equity: number;
	drawdown: number;
	net_pnl: number;
	trade_id: string;
}

export interface RBucket {
	label: string;
	count: number;
}

export interface TagPerf {
	name: string;
	category: string;
	trade_count: number;
	net_pnl: number;
	win_rate: number;
}

export interface CalendarDay {
	date: string;
	net_pnl: number;
	trade_count: number;
}

// --- PLAN-v2 Phase 4 TradeZella DTOs ---

export interface KpiSession {
	net_pnl: number;
	trade_count: number;
	win_rate: number;
	return_pct: number;
}

export interface KpiDashboard {
	net_pnl: number;
	net_pnl_change_pct: number | null;
	sparkline: number[];
	avg_realized_rr: { current: number; target: number };
	win_rate: { rate: number; wins: number; losses: number; breakeven: number };
	profit_factor: number | null;
	sessions: Record<string, KpiSession>;
}

export interface MonthDay {
	net_pnl: number;
	trade_count: number;
	outcome: 'win' | 'loss' | 'be' | 'inactive';
}

export interface MonthlyCalendarDto {
	year: number;
	month: number;
	weeks: { label: string; net_pnl: number; trade_count: number }[];
	days: Record<string, MonthDay>;
	summary: {
		trading_days: number;
		day_win_rate: number;
		winning_days: number;
		losing_days: number;
		breakeven_days: number;
	};
	outcome: { wins: number; losses: number; breakeven: number };
}

export interface ActivityStreaks {
	total_trades: number;
	open_trades: number;
	closed_trades: number;
	winning_trades: number;
	losing_trades: number;
	max_win_streak: number;
	max_loss_streak: number;
	avg_win_streak: number;
	avg_loss_streak: number;
	max_winning_days: number;
	max_losing_days: number;
	trading_days: number;
	avg_daily_volume: number;
	best_trade: { ticket: string; net_pnl: number } | null;
	worst_trade: { ticket: string; net_pnl: number } | null;
}

export interface DirectionStats {
	trades: number;
	wins: number;
	losses: number;
	breakeven: number;
	win_rate: number;
	avg_win: number;
	avg_loss: number;
	best: { ticket: string; net_pnl: number } | null;
	worst: { ticket: string; net_pnl: number } | null;
	avg_win_duration_min: number | null;
	avg_loss_duration_min: number | null;
	max_win_streak: number;
	max_loss_streak: number;
}

export interface RadarProfiles {
	weekday: { day: string; trades: number; wins: number; win_rate: number; net_pnl: number }[];
	sessions: { session: string; trades: number; win_rate: number; net_pnl: number; profit_pct: number }[];
}

export class ApiError extends Error {
	status: number;
	constructor(status: number, message: string) {
		super(message);
		this.status = status;
	}
}

export function errMsg(e: unknown): string {
	if (e instanceof ApiError) return e.status === 0 ? 'Backend unreachable' : e.message;
	if (e instanceof Error) return e.message;
	return 'Unexpected error';
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
	let res: Response;
	try {
		res = await fetch(`${API_BASE}${path}`, init);
	} catch {
		throw new ApiError(0, 'Backend unreachable');
	}
	if (!res.ok) {
		const text = await res.text().catch(() => '');
		throw new ApiError(res.status, text || `Request failed (${res.status})`);
	}
	if (res.status === 204) return undefined as T;
	return (await res.json()) as T;
}

function json(init: RequestInit = {}): RequestInit {
	return { ...init, headers: { 'Content-Type': 'application/json', ...(init.headers ?? {}) } };
}

export const api = {
	health: () => req<{ status: string }>('/api/health'),
	listTrades: async (params?: string): Promise<TradeDto[]> => {
		const data = await req<TradeDto[] | PagedTrades>(`/api/trades${params ?? ''}`);
		return Array.isArray(data) ? data : data.items;
	},
	/** Fetch every trade regardless of server pagination — loops until items.length === total. */
	listAllTrades: async (baseParams?: string): Promise<{ items: TradeDto[]; total: number }> => {
		let page = 1;
		const pageSize = 500;
		let all: TradeDto[] = [];
		let total = 0;
		for (let i = 0; i < 20; i++) {
			const joiner = baseParams?.includes('?') ? '&' : '?';
			const qs = `${baseParams ?? ''}${joiner}page=${page}&page_size=${pageSize}`;
			const data = await req<PagedTrades>(`/api/trades${qs}`);
			if (page === 1) total = data.total;
			all = all.concat(data.items);
			if (all.length >= data.total || data.items.length === 0) break;
			page += 1;
		}
		return { items: all, total };
	},
	listTradesPaged: (params?: string) =>
		req<PagedTrades>(`/api/trades${params ?? '?page=1&page_size=500'}`),
	getTrade: (id: number) => req<TradeDto>(`/api/trades/${id}`),
	openTrade: (payload: Record<string, unknown>) =>
		req<TradeDto>('/api/trades/open', json({ method: 'POST', body: JSON.stringify(payload) })),
	updateTsl: (id: number, current_sl: number) =>
		req<TradeDto>(`/api/trades/${id}/tsl`, json({ method: 'POST', body: JSON.stringify({ current_sl }) })),
	closeTrade: (id: number, payload: Record<string, unknown>) =>
		req<TradeDto>(`/api/trades/${id}/close`, json({ method: 'POST', body: JSON.stringify(payload) })),
	patchTrade: (id: number, patch: Record<string, unknown>) =>
		req<TradeDto>(`/api/trades/${id}`, json({ method: 'PATCH', body: JSON.stringify(patch) })),
	deleteTrade: (id: number, deleteAssets = false) =>
		req<{ deleted: number }>(`/api/trades/${id}${deleteAssets ? '?delete_assets=true' : ''}`, { method: 'DELETE' }),
	backfill: (payload: Record<string, unknown>) =>
		req<{ inserted: string[]; skipped: string[]; total: number }>(
			'/api/trades/backfill',
			json({ method: 'POST', body: JSON.stringify(payload) })
		),
	bulkAccount: (trade_ids: number[], account_id: number | null) =>
		req<{ updated: number }>(
			'/api/trades/bulk-account',
			json({ method: 'POST', body: JSON.stringify({ trade_ids, account_id }) })
		),
	listAccounts: (includeArchived = false) =>
		req<AccountDto[]>(`/api/accounts${includeArchived ? '?include_archived=true' : ''}`),
	createAccount: (payload: Record<string, unknown>) =>
		req<AccountDto>('/api/accounts', json({ method: 'POST', body: JSON.stringify(payload) })),
	updateAccount: (id: number, patch: Record<string, unknown>) =>
		req<AccountDto>(`/api/accounts/${id}`, json({ method: 'PATCH', body: JSON.stringify(patch) })),
	deleteAccount: (id: number) => req<{ deleted: number }>(`/api/accounts/${id}`, { method: 'DELETE' }),
	propStatus: (id: number) => req<PropStatusDto>(`/api/accounts/${id}/prop-status`),
	summary: (accountId?: number | null) =>
		req<SummaryDto>(`/api/analytics/summary${accountId ? `?account_id=${accountId}` : ''}`),
	equityCurve: (accountId?: number | null) =>
		req<{ points: EquityPoint[] }>(
			`/api/analytics/equity-curve${accountId ? `?account_id=${accountId}` : ''}`
		),
	rDistribution: (accountId?: number | null) =>
		req<{ buckets: RBucket[] }>(
			`/api/analytics/r-distribution${accountId ? `?account_id=${accountId}` : ''}`
		),
	tagPerformance: (accountId?: number | null) =>
		req<{ tags: TagPerf[] }>(
			`/api/analytics/tag-performance${accountId ? `?account_id=${accountId}` : ''}`
		),
	calendar: (year?: number, accountId?: number | null) => {
		const qs = new URLSearchParams();
		if (year) qs.set('year', String(year));
		if (accountId) qs.set('account_id', String(accountId));
		const s = qs.toString() ? `?${qs}` : '';
		return req<{ year: number; days: CalendarDay[] }>(`/api/analytics/calendar${s}`);
	},
	kpi: (accountId?: number | null) =>
		req<KpiDashboard>(`/api/analytics/kpi-dashboard${accountId ? `?account_id=${accountId}` : ''}`),
	monthlyCalendar: (year: number, month: number, accountId?: number | null) =>
		req<MonthlyCalendarDto>(
			`/api/analytics/monthly-calendar?year=${year}&month=${month}${accountId ? `&account_id=${accountId}` : ''}`
		),
	activity: (accountId?: number | null) =>
		req<ActivityStreaks>(
			`/api/analytics/activity-and-streaks${accountId ? `?account_id=${accountId}` : ''}`
		),
	longShort: (accountId?: number | null) =>
		req<{ buy: DirectionStats; sell: DirectionStats; all?: DirectionStats }>(
			`/api/analytics/long-short-stats${accountId ? `?account_id=${accountId}` : ''}`
		),
	radar: (accountId?: number | null) =>
		req<RadarProfiles>(`/api/analytics/radar-profiles${accountId ? `?account_id=${accountId}` : ''}`),
	uploadScreenshot: async (id: number, file: File, label: string): Promise<ScreenshotDto> => {
		const form = new FormData();
		form.append('file', file);
		form.append('label', label);
		return req<ScreenshotDto>(`/api/trades/${id}/screenshots`, { method: 'POST', body: form });
	},
	patchScreenshot: (shotId: number, label: string) =>
		req<ScreenshotDto>(`/api/screenshots/${shotId}`, json({ method: 'PATCH', body: JSON.stringify({ label }) })),
	getBrokerOffset: () =>
		req<{ offset_minutes: number | null; label: string | null }>('/api/settings/broker-offset'),
	listNotes: (from?: string, to?: string) => {
		const qs = new URLSearchParams();
		if (from) qs.set('date_from', from);
		if (to) qs.set('date_to', to);
		const suffix = qs.toString() ? `?${qs}` : '';
		return req<DailyNoteDto[]>(`/api/daily-notes${suffix}`);
	},
	getNote: async (day: string): Promise<DailyNoteDto | null> => {
		try {
			return await req<DailyNoteDto>(`/api/daily-notes/${day}`);
		} catch (e) {
			if (e instanceof ApiError && e.status === 404) return null;
			throw e;
		}
	},
	putNote: (day: string, patch: { pre_market?: string | null; eod_review?: string | null }) =>
		req<DailyNoteDto>(`/api/daily-notes/${day}`, json({ method: 'PUT', body: JSON.stringify(patch) })),
	deleteNote: (day: string) => req<{ deleted: string }>(`/api/daily-notes/${day}`, { method: 'DELETE' }),
	thumbUrl: (assetId: string) => `${API_BASE}/api/screenshots/${assetId}/thumbnail`,
	fullUrl: (assetId: string) => `${API_BASE}/api/screenshots/${assetId}/full`
};
