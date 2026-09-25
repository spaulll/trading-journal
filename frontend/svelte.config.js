import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess()
	// NOTE (PLAN Task 0.3): the Node adapter (`adapter({ out: 'build' })`)
	// is configured on the `sveltekit()` Vite plugin in vite.config.ts,
	// which is where SvelteKit 2 reads it from.
};

export default config;
