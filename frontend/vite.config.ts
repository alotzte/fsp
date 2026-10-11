import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  // В dev API идёт через прокси на gateway из docker-compose: один origin, без CORS.
  // Чтобы после входа возвращаться на dev-сервер, в корневом .env задайте FRONTEND_URL=http://localhost:5173.
  const gatewayUrl = env.GATEWAY_URL ?? 'http://localhost:8080'

  return {
    // Префикс, под которым приложение опубликовано (BASE_PATH=/fsp). Пусто — корень домена.
    base: `${env.BASE_PATH ?? ''}/`,
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: { '@': path.resolve(import.meta.dirname, './src') },
    },
    server: {
      proxy: {
        '/api': gatewayUrl,
      },
    },
  }
})
