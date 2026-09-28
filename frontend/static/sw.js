/* Trading Journal — app-shell service worker (read-only offline).
 *
 * Strategy:
 * - Navigations (HTML): network-first, fall back to cache. App opens offline
 *   after at least one online visit.
 * - Static assets (/_app/, /fonts/, icons, css/js/woff2/png): cache-first,
 *   then network, cache successful responses at runtime.
 * - API traffic is NEVER cached here (same-origin /api/* proxy or
 *   cross-origin backend). Live data snapshots live in localStorage
 *   (see $lib/offline-snapshot) so stale PnL is always labelled.
 */

const CACHE = 'tj-shell-v1';
const PRECACHE = ['/', '/manifest.webmanifest', '/icon-192.png', '/icon-512.png'];

self.addEventListener('install', (event) => {
	event.waitUntil(
		caches
			.open(CACHE)
			.then((cache) => cache.addAll(PRECACHE).catch(() => undefined))
			.then(() => self.skipWaiting())
	);
});

self.addEventListener('activate', (event) => {
	event.waitUntil(
		caches
			.keys()
			.then((keys) =>
				Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
			)
			.then(() => self.clients.claim())
	);
});

function isApiRequest(url) {
	return url.pathname.startsWith('/api/');
}

function isCacheableAsset(url) {
	if (url.origin !== self.location.origin) return false;
	return (
		url.pathname.startsWith('/_app/') ||
		url.pathname.startsWith('/fonts/') ||
		/\.(css|js|woff2?|png|ico|svg|webmanifest)$/.test(url.pathname)
	);
}

self.addEventListener('fetch', (event) => {
	const { request } = event;
	if (request.method !== 'GET') return;
	const url = new URL(request.url);

	// Never intercept API traffic — app code serves labelled snapshots instead.
	if (isApiRequest(url)) return;

	// Navigations: try network, fall back to cache (offline shell).
	if (request.mode === 'navigate') {
		event.respondWith(
			fetch(request)
				.then((res) => {
					const copy = res.clone();
					caches.open(CACHE).then((cache) => cache.put(request, copy)).catch(() => undefined);
					return res;
				})
				.catch(() =>
					caches.match(request).then((hit) => hit ?? caches.match('/'))
				)
		);
		return;
	}

	// Static assets: cache-first with runtime fill.
	if (isCacheableAsset(url)) {
		event.respondWith(
			caches.match(request).then(
				(hit) =>
					hit ??
					fetch(request).then((res) => {
						if (res && res.ok) {
							const copy = res.clone();
							caches
								.open(CACHE)
								.then((cache) => cache.put(request, copy))
								.catch(() => undefined);
						}
						return res;
					})
			)
		);
	}
});
