import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig, loadEnv } from 'vite';
import { fileURLToPath } from 'url';
import path, { dirname } from 'path';
import serviceWorker from './plugins/vite-plugin-service-worker';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  // Load env file based on `mode` in the current directory.
  // Set the third parameter to '' to load all env regardless of the `VITE_` prefix.
  const env = loadEnv(mode, process.cwd(), '');

  return {
    plugins: [sveltekit(), serviceWorker()],
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: 'http://backend:8080',
          changeOrigin: true,
          rewrite: (path) => path,
          secure: false,
          configure: (proxy, _options) => {
            proxy.on('error', (err, _req, _res) => {
              console.log('proxy error', err);
            });
            proxy.on('proxyReq', (proxyReq, req, _res) => {
              console.log('Sending Request:', req.method, req.url);
            });
            proxy.on('proxyRes', (proxyRes, req, _res) => {
              console.log('Received Response from:', req.url, proxyRes.statusCode);
            });
          },
        },
        '/api/ws': {
          target: 'ws://backend:8080',
          ws: true,
          changeOrigin: true,
          rewrite: (path) => path,
        },
        // MinIO proxy for presigned URLs (secure media streaming)
        // Use VITE_MINIO_URL env var for remote dev (e.g., Mac -> Linux server)
        // Default: http://minio:9000 (Docker internal, works when frontend runs in Docker)
        '/minio': {
          target: env.VITE_MINIO_URL || 'http://minio:9000',
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/minio/, ''),
          // Set Host header to match what MinIO signed the URL with
          headers: {
            Host: 'minio:9000',
          },
        },
      },
      // Add historyApiFallback to handle client-side routing
      fs: {
        // Allow serving files from parent folders, needed for production builds
        allow: ['../'],
      },
    },
    // Ensure proper handling of client-side routing in production
    build: {
      outDir: 'dist',
      assetsDir: 'assets',
      emptyOutDir: true,
      sourcemap: true,
      rollupOptions: {
        output: {
          manualChunks: undefined,
        },
      },
    },
    define: {
      'import.meta.env.PROD': JSON.stringify(mode === 'production'),
      'import.meta.env.DEV': JSON.stringify(mode !== 'production'),
    },
    base: '/',
    optimizeDeps: {
      exclude: ['@ffmpeg/ffmpeg', '@ffmpeg/util'],
    },
    worker: {
      format: 'es', // Required for FFmpeg.wasm worker threads
    },
  };
});
