import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const apiPort = process.env.API_PORT ?? '8000'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { '/api': `http://localhost:${apiPort}` },
  },
})
