import { defineConfig } from 'vite'

// Interface servie par l'API FastAPI sur /ui/ ; en développement, /api est relayé vers le port 8000.
export default defineConfig({
  base: '/ui/',
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
})
