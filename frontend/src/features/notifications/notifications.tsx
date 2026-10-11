import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router'

import { getListMyChatsQueryKey } from '@/api/generated/chats/chats'
import { getListSentInvitationsQueryKey } from '@/api/generated/employer/employer'
import { getListMyInvitationsQueryKey } from '@/api/generated/invitations/invitations'
import type { NotificationsRead } from '@/api/generated/model'
import { Button } from '@/components/ui/button'
import { useCurrentUser } from '@/features/auth/current-user'
import { messagesCount, useNotifications } from '@/features/notifications/use-notifications'
import { cn } from '@/lib/utils'

const TOAST_MS = 8_000
const BASE_TITLE = 'ФСП Карьера'

/** Число в кружке рядом с пунктом меню; 0 значит ничего. */
export function CountBadge({ count, className }: { count: number; className?: string }) {
  if (count <= 0) return null
  return (
    <span
      className={cn(
        'inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-destructive px-1.5 font-sans text-xs font-semibold text-primary-foreground',
        className,
      )}
    >
      {count > 99 ? '99+' : count}
    </span>
  )
}

type Toast = { text: string; to: string; action: string }

/** Заголовок вкладки «(N) ФСП Карьера» и всплывашка, когда приходит новое. */
export function NotificationsWatcher() {
  const notifications = useNotifications()
  const current = useCurrentUser()
  const location = useLocation()
  const queryClient = useQueryClient()
  const previous = useRef<NotificationsRead | undefined>(undefined)
  const [toast, setToast] = useState<Toast | null>(null)
  const isCandidate = current.status === 'authenticated' && current.user.role === 'candidate'

  useEffect(() => {
    const total = messagesCount(notifications) + (notifications?.invitations_to_answer ?? 0)
    document.title = total > 0 ? `(${total}) ${BASE_TITLE}` : BASE_TITLE
  }, [notifications])

  useEffect(() => {
    const before = previous.current
    previous.current = notifications
    if (!before || !notifications) return
    if (JSON.stringify(before) !== JSON.stringify(notifications)) {
      // Счётчики изменились: открытые списки подтягиваем сразу, не дожидаясь своего опроса.
      for (const queryKey of [
        getListMyChatsQueryKey(),
        getListMyInvitationsQueryKey(),
        getListSentInvitationsQueryKey(),
      ]) {
        void queryClient.invalidateQueries({ queryKey })
      }
    }
    if (messagesCount(notifications) > messagesCount(before)) {
      // В открытой переписке новое сообщение и так видно.
      if (!location.pathname.startsWith('/messages/')) {
        setToast({
          text:
            notifications.chats_to_start > before.chats_to_start
              ? 'Кандидат принял приглашение: напишите ему'
              : 'Новое сообщение',
          to: '/messages',
          action: 'Открыть',
        })
      }
    } else if (notifications.invitations_to_answer > before.invitations_to_answer) {
      setToast(
        isCandidate
          ? { text: 'Новое приглашение', to: '/candidate?tab=invitations', action: 'Посмотреть' }
          : {
              text: 'Новый отклик или ответ кандидата',
              to: '/employer/invitations',
              action: 'Посмотреть',
            },
      )
    }
  }, [notifications, location.pathname, queryClient, isCandidate])

  useEffect(() => {
    if (!toast) return
    const timer = setTimeout(() => setToast(null), TOAST_MS)
    return () => clearTimeout(timer)
  }, [toast])

  if (!toast) return null
  return (
    <div
      role="status"
      className="fixed right-4 bottom-4 z-50 flex max-w-[calc(100vw-2rem)] items-center gap-3 rounded-lg border bg-background p-3 pl-4 text-sm shadow-lg"
    >
      <span>{toast.text}</span>
      <Button asChild size="sm" onClick={() => setToast(null)}>
        <Link to={toast.to}>{toast.action}</Link>
      </Button>
      <Button variant="ghost" size="sm" aria-label="Закрыть" onClick={() => setToast(null)}>
        ✕
      </Button>
    </div>
  )
}
