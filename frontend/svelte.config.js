import adapter from '@sveltejs/adapter-auto';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';
import { resolve } from 'path';

/** @type {import('@sveltejs/kit').Config} */
const config = {
  // Consult https://kit.svelte.dev/docs/integrations#preprocessors
  // for more information about preprocessors
  preprocess: vitePreprocess(),

  kit: {
    // adapter-auto only supports some environments, see https://kit.svelte.dev/docs/adapter-auto for a list.
    // If your environment is not supported or you settled on a specific environment, switch out the adapter.
    // See https://kit.svelte.dev/docs/adapters for more information about adapters.
    adapter: adapter(),
    
    // Specify files directory to properly find the routes
    files: {
      routes: 'src/routes'
    },
    
    // Allow aliasing of paths
    alias: {
      '$components': resolve('./src/components'),
      '$lib': resolve('./src/lib'),
      '$stores': resolve('./src/stores')
    }
  }
};

export default config;
