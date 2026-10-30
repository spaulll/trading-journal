/** In-memory stale-while-revalidate cache for the analytics overview.
 *
 * It lives at module scope so it survives client-side navigation: leaving the
 * Analytics page and coming back paints the last payload immediately instead
 * of a skeleton, then the page revalidates in the background. A component's
 * own `<script>` runs per mount, so a `Map` declared there would be thrown
 * away on every visit — which is the whole thing this fixes.
 *
 * It is deliberately per-tab and not persisted: the labelled localStorage
 * snapshot is the offline path, not the fast path.
 */

import type { AnalyticsOverview } from '$lib/api';

export interface OverviewCacheEntry {
	at: number;
	data: AnalyticsOverview;
}

const cache = new Map<string, OverviewCacheEntry>();

/** The last overview for a key, or undefined when the tab has never seen it. */
export function readOverview(key: string): OverviewCacheEntry | undefined {
	return cache.get(key);
}

/** Record a fresh overview under its key. */
export function writeOverview(key: string, data: AnalyticsOverview): void {
	cache.set(key, { at: Date.now(), data });
}
