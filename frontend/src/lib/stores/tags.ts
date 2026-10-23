import { writable } from 'svelte/store';
import { api, type TagSummaryDto } from '$lib/api';

/**
 * The tag vocabulary shared by every tag field.
 *
 * A tag can be created the moment a trade is saved, so the list is fetched
 * once per modal session rather than cached for the lifetime of the page.
 * Concurrent callers share the same request.
 */
export const tagOptions = writable<TagSummaryDto[]>([]);

let inflight: Promise<void> | null = null;

export function loadTagOptions(): Promise<void> {
	if (inflight) return inflight;
	inflight = api
		.listTags()
		.then((tags) => tagOptions.set(tags))
		.catch(() => {
			// Suggestions are an assist, never a blocker. A failed fetch just
			// leaves the field usable as a plain input.
		})
		.finally(() => {
			inflight = null;
		});
	return inflight;
}
