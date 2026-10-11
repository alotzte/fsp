import { basePath } from '@/api/http-client'

// Вход и регистрация идут переходами браузера на бэк, который редиректит в Keycloak.
// Это навигация, а не fetch: после Keycloak бэк вернёт пользователя на `next`.

export function loginUrl(nextPath: string): string {
  return `${basePath}/api/v1/auth/login?next=${encodeURIComponent(nextPath)}`
}

export function registerUrl(nextPath: string): string {
  return `${basePath}/api/v1/auth/register?next=${encodeURIComponent(nextPath)}`
}
