import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// En développement, /api est relayé vers l'API locale (FastAPI, port 8000).
export default defineConfig({
  plugins: [react()],
  base: '/ui/',
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
})
