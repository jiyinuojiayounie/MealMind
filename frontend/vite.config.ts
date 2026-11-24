import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import type { Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const lanPreview = process.env.VITE_LAN_PREVIEW === '1'

function limitLanApi(): Plugin {
  return {
    name: 'mealmind-lan-api-boundary',
    configureServer(server) {
      server.middlewares.use((request, response, next) => {
        const path = request.url?.split('?')[0]
        if (path !== '/api' && !path?.startsWith('/api/')) return next()
        if (path === '/api/v1/health' && request.method === 'GET') return next()
        response.writeHead(403, { 'Content-Type': 'application/json' })
        response.end(JSON.stringify({ detail: 'Only the read-only health endpoint is available in LAN preview.' }))
      })
    },
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss(), ...(lanPreview ? [limitLanApi()] : [])],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    ...(lanPreview && {
      proxy: {
        '^/api/v1/health(?:\\?|$)': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      },
      fs: {
        allow: [
          fileURLToPath(new URL('./', import.meta.url)),
          fileURLToPath(new URL('../data/recipe_catalog/catalog-v4.json', import.meta.url)),
        ],
      },
    }),
  },
})
