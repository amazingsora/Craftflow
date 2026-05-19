import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 3000,
    watch: {
      usePolling: true,
    },
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        // 如果你的後端 API 本身沒有 /api 開頭，請取消下面這一行的註解
        // rewrite: (path) => path.replace(/^\/api/, '')
      },
    },
  },
})