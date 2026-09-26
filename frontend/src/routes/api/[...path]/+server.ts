// Same-origin API proxy: browsers call https://<domain>/api/* and SvelteKit
// forwards to the backend over loopback. This keeps one public origin behind
// any reverse proxy (no mixed-content, no CORS preflight).
//
// Server env:
//   BACKEND_URL   private backend base (default http://127.0.0.1:8000)
import type { RequestHandler } from './$types';
import { env } from '$env/dynamic/private';

const PASS_HEADERS = ['content-type', 'accept', 'accept-language'];

const handler: RequestHandler = async ({ request, params, url }) => {
	const target = `${env.BACKEND_URL ?? 'http://127.0.0.1:8000'}/api/${params.path ?? ''}${url.search}`;
	const headers = new Headers();
	for (const name of PASS_HEADERS) {
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
		for (const name of ['content-type', 'content-disposition']) {
			const value = upstream.headers.get(name);
			if (value) out.set(name, value);
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
