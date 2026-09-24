import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // 預設只綁本機；Docker 內由 docker-compose 設 VITE_HOST=0.0.0.0
    host: process.env.VITE_HOST || '127.0.0.1',
    port: 3000,
    watch: {
      usePolling: true,
    },
    proxy: {
      '/api': {
        // 用 127.0.0.1：後端只綁 IPv4 本機，localhost 在部分系統會先解析成 ::1
        target: process.env.VITE_API_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
        // 如果你的後端 API 本身沒有 /api 開頭，請取消下面這一行的註解
        // rewrite: (path) => path.replace(/^\/api/, '')
      },
    },
  },
})