import { env } from '$env/dynamic/public';

/** Backend base URL. Override per environment with PUBLIC_API_BASE. */
export const API_BASE: string = env.PUBLIC_API_BASE ?? 'http://127.0.0.1:9000';

export interface TagDto {
	id: number;
	name: string;
	category: string;
}

/** A tag with the numbers the taxonomy page shows. */
export interface TagSummaryDto extends TagDto {
	trade_count: number;
	net_pnl: number;
	win_rate: number | null;
	last_used: string | null;
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
	/** Broker-booked amounts, in `quote_currency`. */
	gross_pnl: number | null;
	fees: number | null;
	net_pnl: number | null;
	quote_currency: string;
	/** The same amounts converted at the close-day FX rate (USD totals). */
	gross_pnl_usd: number | null;
	net_pnl_usd: number | null;
	/** Quote P&L exists but no FX rate could convert it. */
	fx_missing: boolean;
	r_multiple: number | null;
	initial_risk: number | null;
	realized_risk: number | null;
	risk_unit: string | null;
	status: string;
	thesis: string | null;
	review_notes: string | null;
	created_at: string;
	updated_at: string;
	tags: TagDto[];
	screenshots: ScreenshotDto[];
}

export interface SymbolSpecDto {
	id: number;
	symbol: string;
	display: string;
	contract_size: number;
	pip_size: number;
	quote_currency: string;
	category: string;
	enabled: boolean;
}

export interface SymbolPreviewDto {
	symbol: string;
	registered: boolean;
	display: string;
	category: string;
	contract_size: number | null;
	pip_size: number | null;
	quote_currency: string;
	/** Reward in the quote currency; `gross_pnl_usd` is its USD view. */
	gross_pnl: number | null;
	gross_pnl_usd: number | null;
	r_multiple: number | null;
	initial_risk: number | null;
	realized_risk: number | null;
	risk_unit: string | null;
	distance: number | null;
	pips: number | null;
	risk_distance: number | null;
	risk_pips: number | null;
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

/** Where the trading day rolls over, and the day the app calls today. */
export interface TradingDayDto {
	boundary_hour: number;
	timezone: string;
	label: string;
	today: string;
	default_boundary_hour: number;
	default_timezone: string;
}

/** How the day lined up with the pre-market plan. */
export interface AdherenceDto {
	day: string;
	has_plan: boolean;
	score: number | null;
	planned_setups: string[];
	traded_setups: string[];
	setup_match: number | null;
	planned_size: number | null;
	size_match: number | null;
	trades: number;
	discipline_breach: boolean;
	notes: string[];
}

export interface AccountDto {
	id: number;
	firm: string;
	alias: string;
	login: string | null;
	phase: string;
	start_balance: number;
	/** Currency the start balance and prop limits are declared in. */
	base_currency: string;
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
	/** Currency every figure below is stated in (account base or ?base=). */
	base_currency: string;
	account_base_currency: string;
	start_balance: number;
	balance: number;
	total_net: number;
	/** The same net across all currencies, in USD. */
	total_net_usd: number;
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
	/** Conversion provenance: missing rates and stale-rate fallbacks. */
	fx: { missing: number; fallback: number; max_fallback_days: number };
}

export interface LedgerCounts {
	ALL: number;
	OPEN: number;
	CLOSED: number;
}

export interface PagedTrades {
	items: TradeDto[];
	total: number;
	page: number;
	page_size: number;
	/** How many trades each status tab holds under the current filter. */
	counts?: LedgerCounts;
}

export interface SyncResult {
	inserted: number;
	updated: number;
	total: number;
}

export interface InsightReportDto {
	id: number;
	date_from: string;
	date_to: string;
	markdown: string;
	model: string;
	created_at: string;
}

export type WeekendReviewResult =
	| { status: 'ok'; date_from: string; date_to: string; report: InsightReportDto }
	| { status: 'empty'; date_from: string; date_to: string; detail: string };

export interface SummaryDto {
	total_trades: number;
	open_trades: number;
	wins: number;
	losses: number;
	breakeven: number;
	/** Closed trades with no net P&L — the symbol had no contract. */
	unpriced: number;
	net_pnl: number;
	win_rate: number;
	profit_factor: number | null;
	expectancy: number;
	avg_win: number;
	avg_loss: number;
	/** The average R of the closed trades in the filter. */
	avg_r: number | null;
	max_drawdown: number;
	/** Quote-currency totals behind the USD figure, e.g. { JPY: 5000 }. */
	by_currency?: Record<string, number>;
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
	unpriced: number;
	net_pnl: number;
	win_rate: number;
}

/** The shared metric row behind the depth tables. */
export interface PerformanceBucket {
	trade_count: number;
	priced: number;
	unpriced: number;
	wins: number;
	losses: number;
	breakeven: number;
	net_pnl: number;
	win_rate: number;
	expectancy: number;
	profit_factor: number | null;
	avg_r: number | null;
	r_trades: number;
	by_currency?: Record<string, number>;
}

export interface SymbolPerformanceRow extends PerformanceBucket {
	symbol: string;
	display: string;
	registered: boolean;
	category: string | null;
	contract_size: number | null;
}

export interface SymbolPerformance {
	symbols: SymbolPerformanceRow[];
	totals: PerformanceBucket;
}

export interface MatrixCell extends PerformanceBucket {
	symbol: string;
}

export interface SetupMatrixRow extends PerformanceBucket {
	setup: string | null;
	label: string;
	is_untagged: boolean;
	cells: MatrixCell[];
}

export interface SetupMatrix {
	setups: string[];
	symbols: string[];
	rows: SetupMatrixRow[];
	column_totals: MatrixCell[];
	grand_total: PerformanceBucket;
}

export interface SetupConfidenceRow {
	name: string;
	category: string;
	trade_count: number;
	priced: number;
	unpriced: number;
	wins: number;
	losses: number;
	breakeven: number;
	decided: number;
	win_rate: number;
	net_pnl: number;
	expectancy: number;
	std_dev: number | null;
	standard_error: number | null;
	ci_low: number | null;
	ci_high: number | null;
	ci_level: number;
	sufficient: boolean;
}

export interface SetupConfidence {
	min_sample: number;
	ci_level: number;
	tags: SetupConfidenceRow[];
	insufficient: number;
}

export interface DrawdownGroup extends PerformanceBucket {
	key: string;
	label: string;
	peak: number;
	max_drawdown: number;
	current_drawdown: number;
}

export interface DrawdownBreakdown {
	group_by: 'account' | 'setup';
	overall: DrawdownGroup;
	groups: DrawdownGroup[];
}

export interface RiskOfRuinRow {
	name: string;
	trade_count: number;
	decided: number;
	wins: number;
	losses: number;
	breakeven: number;
	unpriced: number;
	win_rate: number;
	avg_win: number | null;
	avg_loss: number | null;
	payoff_ratio: number | null;
	expectancy_r: number | null;
	net_pnl: number;
	avg_r: number | null;
	risk_per_trade: number | null;
	risk_source: 'explicit' | 'realized' | 'initial' | 'missing';
	risk_units: number | null;
	risk_of_ruin: number | null;
	sufficient: boolean;
}

export interface RiskOfRuin {
	account_size: number | null;
	account_size_source: string;
	risk_per_trade_override: number | null;
	min_sample: number;
	method: string;
	detail: string | null;
	setups: RiskOfRuinRow[];
	insufficient: number;
}

export interface CalendarDay {
	date: string;
	net_pnl: number;
	trade_count: number;
	unpriced: number;
	by_currency?: Record<string, number>;
}

// --- PLAN-v2 Phase 4 TradeZella DTOs ---

export interface KpiSession {
	net_pnl: number;
	trade_count: number;
	unpriced: number;
	win_rate: number;
	return_pct: number;
}

export interface KpiDashboard {
	net_pnl: number;
	net_pnl_change_pct: number | null;
	sparkline: number[];
	avg_realized_rr: { current: number; target: number };
	win_rate: { rate: number; wins: number; losses: number; breakeven: number; unpriced: number };
	profit_factor: number | null;
	sessions: Record<string, KpiSession>;
}

export interface MonthDay {
	net_pnl: number;
	trade_count: number;
	unpriced: number;
	outcome: 'win' | 'loss' | 'be' | 'unpriced' | 'inactive';
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
		unpriced_days: number;
	};
	outcome: { wins: number; losses: number; breakeven: number; unpriced: number };
}

export interface ActivityStreaks {
	total_trades: number;
	open_trades: number;
	closed_trades: number;
	winning_trades: number;
	losing_trades: number;
	unpriced_trades: number;
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
	unpriced: number;
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
	weekday: {
		day: string;
		trades: number;
		wins: number;
		unpriced: number;
		win_rate: number;
		net_pnl: number;
	}[];
	sessions: {
		session: string;
		trades: number;
		unpriced: number;
		win_rate: number;
		net_pnl: number;
		profit_pct: number;
	}[];
}

export class ApiError extends Error {
	status: number;
	constructor(status: number, message: string) {
		super(message);
		this.status = status;
	}
}

/** FastAPI error bodies are {"detail": "..."} or {"detail": [{msg}]} — show the human part. */
function humanizeError(raw: string, status: number): string {
	const text = raw.trim();
	if (text.startsWith('{') || text.startsWith('[')) {
		try {
			const parsed = JSON.parse(text) as { detail?: unknown };
			const detail = parsed.detail;
			if (typeof detail === 'string' && detail.trim()) return detail.trim();
			if (Array.isArray(detail)) {
				const msgs = detail
					.map((d) => (d && typeof d === 'object' ? (d as { msg?: string }).msg : null))
					.filter((m): m is string => Boolean(m));
				if (msgs.length) return msgs.join(' · ');
			}
		} catch {
			/* not JSON — fall through to the raw text */
		}
	}
	return text || `Request failed (${status})`;
}

export function errMsg(e: unknown): string {
	if (e instanceof ApiError) {
		// status 0 = the request never reached the backend (or timed out).
		if (e.status === 0) return e.message || 'Backend unreachable';
		return humanizeError(e.message, e.status);
	}
	if (e instanceof Error) return e.message;
	return 'Unexpected error';
}

/** Requests that should not hang forever — the UI must always end with an error. */
const DEFAULT_TIMEOUT_MS = 60_000;

async function req<T>(path: string, init?: RequestInit, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<T> {
	let res: Response;
	try {
		res = await fetch(`${API_BASE}${path}`, {
			...init,
			signal: init?.signal ?? AbortSignal.timeout(timeoutMs)
		});
	} catch (e) {
		if (e instanceof DOMException && e.name === 'TimeoutError') {
			throw new ApiError(0, 'Request timed out — the server took too long');
		}
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
	/** Fetch every trade that matches a filter, whatever the server pagination — loops until items.length === total. */
	listAllTrades: async (
		baseParams?: string
	): Promise<{ items: TradeDto[]; total: number; counts: LedgerCounts }> => {
		let page = 1;
		const pageSize = 500;
		let all: TradeDto[] = [];
		let total = 0;
		let counts: LedgerCounts = { ALL: 0, OPEN: 0, CLOSED: 0 };
		for (let i = 0; i < 20; i++) {
			const joiner = baseParams?.includes('?') ? '&' : '?';
			const qs = `${baseParams ?? ''}${joiner}page=${page}&page_size=${pageSize}`;
			const data = await req<PagedTrades>(`/api/trades${qs}`);
			if (page === 1) {
				total = data.total;
				counts = data.counts ?? counts;
			}
			all = all.concat(data.items);
			if (all.length >= data.total || data.items.length === 0) break;
			page += 1;
		}
		return { items: all, total, counts };
	},
	listTradesPaged: (params?: string) =>
		req<PagedTrades>(`/api/trades${params ?? '?page=1&page_size=500'}`),
	/** The ids of every trade a filter matches — the bulk move's work list. */
	listTradeIds: (params?: string) => req<{ ids: number[]; total: number }>(`/api/trades/ids${params ?? ''}`),
	/** The CSV of a filter — the server answers with a file download. */
	exportTradesUrl: (params?: string) => `${API_BASE}/api/trades/export${params ?? ''}`,
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
		req<{ updated: number; skipped: Array<number | string>; requested: number }>(
			'/api/trades/bulk-account',
			json({ method: 'POST', body: JSON.stringify({ trade_ids, account_id }) })
		),
	listTags: () => req<TagSummaryDto[]>('/api/tags'),
	patchTag: (id: number, patch: { name?: string; category?: string }) =>
		req<TagDto>(`/api/tags/${id}`, json({ method: 'PATCH', body: JSON.stringify(patch) })),
	mergeTags: (source_id: number, target_id: number) =>
		req<{ merged: string; into: string; trades: number; tag: TagDto }>(
			'/api/tags/merge',
			json({ method: 'POST', body: JSON.stringify({ source_id, target_id }) })
		),
	listAccounts: (includeArchived = false) =>
		req<AccountDto[]>(`/api/accounts${includeArchived ? '?include_archived=true' : ''}`),
	createAccount: (payload: Record<string, unknown>) =>
		req<AccountDto>('/api/accounts', json({ method: 'POST', body: JSON.stringify(payload) })),
	updateAccount: (id: number, patch: Record<string, unknown>) =>
		req<AccountDto>(`/api/accounts/${id}`, json({ method: 'PATCH', body: JSON.stringify(patch) })),
	deleteAccount: (id: number) => req<{ deleted: number }>(`/api/accounts/${id}`, { method: 'DELETE' }),	propStatus: (id: number) => req<PropStatusDto>(`/api/accounts/${id}/prop-status`),
	listSymbols: (includeDisabled = false) =>
		req<SymbolSpecDto[]>(`/api/symbols${includeDisabled ? '?include_disabled=true' : ''}`),
	createSymbol: (payload: Record<string, unknown>) =>
		req<SymbolSpecDto>('/api/symbols', json({ method: 'POST', body: JSON.stringify(payload) })),
	updateSymbol: (id: number, patch: Record<string, unknown>) =>
		req<SymbolSpecDto>(`/api/symbols/${id}`, json({ method: 'PATCH', body: JSON.stringify(patch) })),
	/** The server's price for one position: gross, R and risk. */
	previewSymbol: (params: Record<string, string | number | undefined>) => {
		const qs = new URLSearchParams();
		for (const [key, value] of Object.entries(params)) {
			if (value === undefined || value === null || value === '') continue;
			qs.set(key, String(value));
		}
		return req<SymbolPreviewDto>(`/api/symbols/preview?${qs.toString()}`);
	},
	/** The summary over a filter — a query string, or one account id. */
	summary: (params?: string | number | null) => {
		const qs =
			typeof params === 'string'
				? params
				: params
					? `?account_id=${params}`
					: '';
		return req<SummaryDto>(`/api/analytics/summary${qs}`);
	},
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
	symbolPerformance: (accountId?: number | null) =>
		req<SymbolPerformance>(
			`/api/analytics/symbol-performance${accountId ? `?account_id=${accountId}` : ''}`
		),
	setupMatrix: (accountId?: number | null) =>
		req<SetupMatrix>(
			`/api/analytics/setup-matrix${accountId ? `?account_id=${accountId}` : ''}`
		),
	setupConfidence: (accountId?: number | null) =>
		req<SetupConfidence>(
			`/api/analytics/setup-confidence${accountId ? `?account_id=${accountId}` : ''}`
		),
	drawdown: (groupBy: 'account' | 'setup', accountId?: number | null) => {
		const qs = new URLSearchParams({ group_by: groupBy });
		if (accountId) qs.set('account_id', String(accountId));
		return req<DrawdownBreakdown>(`/api/analytics/drawdown?${qs.toString()}`);
	},
	riskOfRuin: (accountId?: number | null) =>
		req<RiskOfRuin>(
			`/api/analytics/risk-of-ruin${accountId ? `?account_id=${accountId}` : ''}`
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
	/** Where the trading day rolls over — and which day the app calls today. */
	getTradingDay: () => req<TradingDayDto>('/api/settings/trading-day'),
	putTradingDay: (patch: { boundary_hour?: number; timezone?: string }) =>
		req<TradingDayDto>('/api/settings/trading-day', json({ method: 'PUT', body: JSON.stringify(patch) })),
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
	putNote: (
		day: string,
		patch: { pre_market?: string | null; eod_review?: string | null; discipline_breach?: boolean }
	) => req<DailyNoteDto>(`/api/daily-notes/${day}`, json({ method: 'PUT', body: JSON.stringify(patch) })),
	/** The plan score for a day — did the day follow the pre-market note? */
	adherence: (day: string) => req<AdherenceDto>(`/api/daily-notes/${day}/adherence`),	deleteNote: (day: string) => req<{ deleted: string }>(`/api/daily-notes/${day}`, { method: 'DELETE' }),
	weekendReview: (from?: string, to?: string) =>
		req<WeekendReviewResult>(
			'/api/insights/weekend-review',
			json({ method: 'POST', body: JSON.stringify({ date_from: from ?? null, date_to: to ?? null }) }),
			// The provider can take a while, and the backend retries on rate limits.
			240_000
		),
	listInsightReports: () => req<InsightReportDto[]>('/api/insights/reports'),
	deleteInsightReport: (id: number) =>
		req<{ deleted: number }>(`/api/insights/reports/${id}`, { method: 'DELETE' }),
	thumbUrl: (assetId: string) => `${API_BASE}/api/screenshots/${assetId}/thumbnail`,
	fullUrl: (assetId: string) => `${API_BASE}/api/screenshots/${assetId}/full`
};
