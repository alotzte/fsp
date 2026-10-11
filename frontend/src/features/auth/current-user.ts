import { useGetMe } from '@/api/generated/me/me'
import type { MeRead, UserRole } from '@/api/generated/model'
import type { ApiError } from '@/api/http-client'

export type CurrentUserState =
  | { status: 'loading' }
  | { status: 'anonymous' }
  | { status: 'error'; error: ApiError }
  | { status: 'authenticated'; user: MeRead }

const HTTP_UNAUTHORIZED = 401

/** Текущий пользователь по cookie сессии. 401 от /me это не ошибка, а «не вошёл». */
export function useCurrentUser(): CurrentUserState {
  const me = useGetMe()
  if (me.isPending) return { status: 'loading' }
  if (me.isError) {
    return me.error.status === HTTP_UNAUTHORIZED
      ? { status: 'anonymous' }
      : { status: 'error', error: me.error }
  }
  return { status: 'authenticated', user: me.data }
}

export function cabinetPath(role: UserRole): string {
  return role === 'candidate' ? '/candidate' : '/employer'
}

/** Пускает только пути внутри сайта: иначе параметр next станет открытым редиректом. */
export function safeNextPath(next: string | null): string | null {
  if (!next || !next.startsWith('/') || next.startsWith('//')) return null
  return next
}
