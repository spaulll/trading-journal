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
	timestamp_open: string | null;
	timestamp_close: string | null;
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
	listTradesPaged: (params?: string) =>
		req<PagedTrades>(`/api/trades${params ?? '?page=1&page_size=50'}`),
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
	summary: () => req<SummaryDto>('/api/analytics/summary'),
	equityCurve: () => req<{ points: EquityPoint[] }>('/api/analytics/equity-curve'),
	rDistribution: () => req<{ buckets: RBucket[] }>('/api/analytics/r-distribution'),
	tagPerformance: () => req<{ tags: TagPerf[] }>('/api/analytics/tag-performance'),
	calendar: (year?: number) =>
		req<{ year: number; days: CalendarDay[] }>(`/api/analytics/calendar${year ? `?year=${year}` : ''}`),
	kpi: () => req<KpiDashboard>('/api/analytics/kpi-dashboard'),
	monthlyCalendar: (year: number, month: number) =>
		req<MonthlyCalendarDto>(`/api/analytics/monthly-calendar?year=${year}&month=${month}`),
	activity: () => req<ActivityStreaks>('/api/analytics/activity-and-streaks'),
	longShort: () => req<{ buy: DirectionStats; sell: DirectionStats }>('/api/analytics/long-short-stats'),
	radar: () => req<RadarProfiles>('/api/analytics/radar-profiles'),
	uploadScreenshot: async (id: number, file: File, label: string): Promise<ScreenshotDto> => {
		const form = new FormData();
		form.append('file', file);
		form.append('label', label);
		return req<ScreenshotDto>(`/api/trades/${id}/screenshots`, { method: 'POST', body: form });
	},
	thumbUrl: (assetId: string) => `${API_BASE}/api/screenshots/${assetId}/thumbnail`,
	fullUrl: (assetId: string) => `${API_BASE}/api/screenshots/${assetId}/full`
};
