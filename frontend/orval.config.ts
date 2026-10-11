import { defineConfig } from 'orval'

export default defineConfig({
  backend: {
    input: {
      target: process.env.OPENAPI_URL ?? 'http://localhost:8080/openapi.json',
      // /health — служебная ручка для Docker, не под /api: из браузера она недоступна.
      // auth-browser-redirects — переходы браузера на Keycloak, их открывают навигацией, а не fetch.
      filters: { mode: 'exclude', tags: ['health', 'auth-browser-redirects'] },
    },
    output: {
      mode: 'tags-split',
      target: 'src/api/generated',
      schemas: 'src/api/generated/model',
      client: 'react-query',
      httpClient: 'fetch',
      clean: true,
      prettier: true,
      override: {
        mutator: { path: 'src/api/http-client.ts', name: 'httpClient' },
        fetch: { includeHttpResponseReturnType: false },
      },
    },
  },
})
