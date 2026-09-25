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
	trade_id: string;
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
	tags: TagDto[];
	screenshots: ScreenshotDto[];
}

export interface SyncResult {
	inserted: number;
	updated: number;
	total: number;
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
	listTrades: () => req<TradeDto[]>('/api/trades'),
	getTrade: (id: number) => req<TradeDto>(`/api/trades/${id}`),
	patchTrade: (id: number, patch: Record<string, unknown>) =>
		req<TradeDto>(`/api/trades/${id}`, json({ method: 'PATCH', body: JSON.stringify(patch) })),
	deleteTrade: (id: number) => req<{ deleted: number }>(`/api/trades/${id}`, { method: 'DELETE' }),
	syncBot: () => req<SyncResult>('/api/trades/sync-bot', { method: 'POST' }),
	uploadScreenshot: async (id: number, file: File, label: string): Promise<ScreenshotDto> => {
		const form = new FormData();
		form.append('file', file);
		form.append('label', label);
		return req<ScreenshotDto>(`/api/trades/${id}/screenshots`, { method: 'POST', body: form });
	},
	thumbUrl: (assetId: string) => `${API_BASE}/api/screenshots/${assetId}/thumbnail`,
	fullUrl: (assetId: string) => `${API_BASE}/api/screenshots/${assetId}/full`
};
