// Same-origin API proxy: browsers call https://<domain>/api/* and SvelteKit
// forwards to the backend over loopback. This keeps one public origin behind
// any reverse proxy (no mixed-content, no CORS preflight).
//
// The whitelists below are deliberate: this proxy rebuilds the response, so
// anything not named here is dropped. Caching headers (ETag/Cache-Control)
// and the conditional-request headers must survive, or the browser can never
// revalidate and every response is a full body.
//
// Server env:
//   BACKEND_URL   private backend base (default http://127.0.0.1:8000)
import type { RequestHandler } from './$types';
import { env } from '$env/dynamic/private';

// Request headers the backend needs to see. The conditional ones let a
// revalidation reach it so it can answer 304 instead of resending the body.
const PASS_REQUEST_HEADERS = [
	'content-type',
	'accept',
	'accept-language',
	'if-none-match',
	'if-modified-since',
	'range'
];

// Response headers a caching client needs. The body is passed through
// untouched, so the upstream Content-Length stays valid.
const PASS_RESPONSE_HEADERS = [
	'content-type',
	'content-disposition',
	'content-length',
	'etag',
	'last-modified',
	'cache-control',
	'vary'
];

const handler: RequestHandler = async ({ request, params, url }) => {
	const target = `${env.BACKEND_URL ?? 'http://127.0.0.1:8000'}/api/${params.path ?? ''}${url.search}`;
	const headers = new Headers();
	for (const name of PASS_REQUEST_HEADERS) {
		const value = request.headers.get(name);
		if (value) headers.set(name, value);
	}
	try {
		const upstream = await fetch(target, {
			method: request.method,
			headers,
			body:
				request.method === 'GET' || request.method === 'HEAD'
					? undefined
					: await request.arrayBuffer()
		});
		const out = new Headers();
		for (const name of PASS_RESPONSE_HEADERS) {
			const value = upstream.headers.get(name);
			if (value) out.set(name, value);
		}
		// A 304 (and 204) must carry no body.
		if (upstream.status === 304 || upstream.status === 204) {
			return new Response(null, { status: upstream.status, headers: out });
		}
		return new Response(upstream.body, { status: upstream.status, headers: out });
	} catch {
		return Response.json({ detail: 'backend unreachable' }, { status: 502 });
	}
};

export const GET = handler;
export const POST = handler;
export const PUT = handler;
export const PATCH = handler;
export const DELETE = handler;
export const OPTIONS = handler;
export const HEAD = handler;
