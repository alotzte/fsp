import { useGetMyNotifications } from '@/api/generated/chats/chats'
import type { NotificationsRead } from '@/api/generated/model'
import { useCurrentUser } from '@/features/auth/current-user'

// Опрос, а не push (архитектура §5.2): счётчики приходят одним лёгким запросом. Опрашиваем и в фоне,
// чтобы «(N)» в заголовке вкладки появлялось, пока открыто другое окно.
const POLL_MS = 10_000

/** Счётчики того, что ждёт действия пользователя (шапка, вкладки, заголовок). */
export function useNotifications(): NotificationsRead | undefined {
  const current = useCurrentUser()
  const enabled = current.status === 'authenticated' && current.user.role !== null
  const query = useGetMyNotifications({
    query: { enabled, refetchInterval: POLL_MS, refetchIntervalInBackground: true, staleTime: 0 },
  })
  return enabled ? query.data : undefined
}

/** Сообщения, которые ждут: непрочитанные и новые контакты, где ещё никто не написал. */
export function messagesCount(n: NotificationsRead | undefined): number {
  return n ? n.unread_messages + n.chats_to_start : 0
}
