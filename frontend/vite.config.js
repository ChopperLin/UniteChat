import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const backendHost = process.env.BACKEND_HOST || '127.0.0.1'
const backendPort = process.env.BACKEND_PORT || '5847'
const backendTarget = `http://${backendHost}:${backendPort}`
const frontendPort = parseInt(process.env.VITE_PORT || '3847', 10)

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: frontendPort,
    proxy: {
      '/api': {
        target: backendTarget,
        changeOrigin: true
      }
    }
  }
})
