import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'

import { getGetMyNotificationsQueryKey, getListMyChatsQueryKey } from '@/api/generated/chats/chats'
import {
  getListInvitationMessagesQueryKey,
  useListInvitationMessages,
  usePostInvitationMessage,
} from '@/api/generated/invitations/invitations'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { formatDateTime } from '@/features/invitations/format'
import { cn } from '@/lib/utils'

// Переписка обновляется опросом: для чата двух сторон WebSocket не нужен. Только пока вкладка
// видна: чтение отмечает сообщения прочитанными, а в фоне они должны копиться в счётчике.
const POLL_MS = 3000

/** Переписка по принятому приглашению: одна и та же для кандидата и работодателя.
 * `readOnly`: кандидат закрыл компании доступ к контактам, поэтому история видна, а писать нельзя. */
export function ChatPanel({
  invitationId,
  readOnly = false,
  className,
}: {
  invitationId: string
  readOnly?: boolean
  /** Высота ленты сообщений, по умолчанию max-h-80. */
  className?: string
}) {
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState('')
  const messages = useListInvitationMessages(invitationId, {
    // Закрытая переписка не меняется: опрашивать незачем.
    query: { refetchInterval: readOnly ? false : POLL_MS, staleTime: 0 },
  })
  const post = usePostInvitationMessage({
    mutation: {
      onSuccess: () => {
        setDraft('')
        void queryClient.invalidateQueries({
          queryKey: getListInvitationMessagesQueryKey(invitationId),
        })
      },
    },
  })
  const send = () => {
    if (draft.trim() && !post.isPending) {
      post.mutate({ invitationId, data: { body: draft.trim() } })
    }
  }

  // Прочитанное бэк отмечает при загрузке ленты: обновляем счётчики в шапке и списке чатов.
  const lastId = messages.data?.at(-1)?.id
  useEffect(() => {
    if (lastId === undefined) return
    void queryClient.invalidateQueries({ queryKey: getGetMyNotificationsQueryKey() })
    void queryClient.invalidateQueries({ queryKey: getListMyChatsQueryKey() })
  }, [lastId, queryClient])

  // Новое сообщение: прокрутить вниз, как в мессенджере.
  const listRef = useRef<HTMLOListElement>(null)
  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight })
  }, [lastId])

  return (
    <div className="flex flex-col gap-3">
      <ol
        ref={listRef}
        className={cn('flex max-h-80 flex-col gap-2 overflow-y-auto', className)}
        aria-live="polite"
      >
        {messages.data?.length === 0 && (
          <li className="text-sm text-muted-foreground">
            {readOnly ? 'Сообщений не было.' : 'Сообщений пока нет, напишите первым.'}
          </li>
        )}
        {messages.data?.map((message) => (
          <li
            key={message.id}
            className={cn(
              'flex max-w-[85%] flex-col gap-1 rounded-lg px-3 py-2 text-sm',
              message.mine ? 'self-end bg-primary text-primary-foreground' : 'self-start bg-muted',
            )}
          >
            <span className="[overflow-wrap:anywhere] whitespace-pre-line">{message.body}</span>
            <span
              className={cn(
                'text-xs',
                message.mine ? 'text-primary-foreground/80' : 'text-muted-foreground',
              )}
            >
              {formatDateTime(message.created_at)}
            </span>
          </li>
        ))}
      </ol>
      {(messages.isError || post.isError) && (
        <Alert variant="destructive">
          <AlertDescription>{(messages.error ?? post.error)?.message}</AlertDescription>
        </Alert>
      )}
      {readOnly ? (
        <p className="text-sm text-muted-foreground">
          Доступ к контактам закрыт: переписка только для чтения.
        </p>
      ) : (
        <div className="flex flex-col gap-1">
          <div className="flex items-end gap-2">
            <Textarea
              aria-label="Сообщение"
              rows={2}
              maxLength={2000}
              value={draft}
              placeholder="Сообщение"
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault()
                  send()
                }
              }}
            />
            <Button disabled={!draft.trim() || post.isPending} onClick={send}>
              Отправить
            </Button>
          </div>
          <span className="text-xs text-muted-foreground">
            Enter: отправить, Shift+Enter: новая строка
          </span>
        </div>
      )}
    </div>
  )
}
