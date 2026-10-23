import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  // Where the FastAPI server runs. Override in dashboard/.env.local (see .env.example).
  const env = loadEnv(mode, process.cwd(), '')
  const serverUrl = env.VITE_SERVER_URL || 'http://127.0.0.1:8000'

  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: serverUrl,
          changeOrigin: true,
        },
        '/health': {
          target: serverUrl,
          changeOrigin: true,
        },
        '/ws': {
          target: serverUrl.replace(/^http/, 'ws'),
          ws: true,
        },
      },
    },
  }
})
