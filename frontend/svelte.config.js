import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	// Consult https://svelte.dev/docs/kit/integrations
	// for more information about preprocessors
	preprocess: vitePreprocess(),

	kit: {
		// Use static adapter for SPA mode
		adapter: adapter({
			pages: 'dist',
			assets: 'dist',
			fallback: 'index.html',
			precompress: false,
			strict: true
		}),

		// SPA mode configuration
		prerender: {
			handleHttpError: 'warn',
			handleMissingId: 'warn'
		},

		// Alias configuration (matches vite.config.ts)
		alias: {
			'$lib': './src/lib',
			'$components': './src/components',
			'$stores': './src/stores',
		}
	}
};

export default config;
