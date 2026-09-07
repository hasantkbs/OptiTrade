import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
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
