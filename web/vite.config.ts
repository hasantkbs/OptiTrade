import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Deployed under an existing site's /optitrade/ path (Algorix
  // integrated deployment), not at a domain root - VITE_BASE_PATH is
  // set at build time (web/Dockerfile) so every emitted asset URL and
  // the router's basename (src/main.tsx) agree. Defaults to root '/'
  // so local dev and `vite preview` are unaffected.
  base: process.env.VITE_BASE_PATH || '/',
  build: {
    // Default 'assets' collides with this app's own /assets and
    // /assets/:symbol client routes: nginx's static-file layer sees a
    // real assets/ directory on disk and intercepts those routes before
    // the SPA fallback ever runs (found via live validation under
    // /optitrade/ - the router route is unrelated to Vite's build
    // output, but the directory name was shared). Renamed to something
    // no app route will ever collide with.
    assetsDir: '_assets',
  },
  server: {
    proxy: {
      // Local dev only: forwards /api/* to the backend directly (no
      // reverse proxy in dev - see docker-compose.override.yml, which
      // exposes api on 127.0.0.1:8000). Production builds talk to the
      // real domain through nginx (SERVER STEP 5) instead - see
      // src/api/client.ts for how the base URL is chosen.
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: true,
  },
})
