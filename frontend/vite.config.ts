import adapter from '@sveltejs/adapter-node';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},

			// Production Node adapter: `node build` serves on :3000 with ORIGIN.
			// (Kit 2 reads the adapter from the Vite plugin; svelte.config.js
			// keeps preprocess only — see PLAN Task 0.3.)
			adapter: adapter({ out: 'build' })
		})
	]
});
