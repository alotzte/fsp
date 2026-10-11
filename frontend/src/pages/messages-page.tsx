import { Link, useParams } from 'react-router'

import { useListMyChats } from '@/api/generated/chats/chats'
import type { ChatRead } from '@/api/generated/model'
import { ErrorState } from '@/components/error-state'
import { PageLoader } from '@/components/page-loader'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useCurrentUser } from '@/features/auth/current-user'
import { CompanyLogo } from '@/features/companies/company-logo'
import { candidatePath } from '@/features/hiring/paths'
import { ChatPanel } from '@/features/invitations/chat-panel'
import { formatDateTime } from '@/features/invitations/format'
import { CountBadge } from '@/features/notifications/notifications'
import { cn } from '@/lib/utils'

// Список тоже опрашивается: новые переписки и превью последних сообщений без перезагрузки.
const POLL_MS = 10_000

/** Все переписки по принятым приглашениям: слева список, справа выбранная. На телефоне
 * по очереди: список, затем переписка с кнопкой «назад». */
export function MessagesPage() {
  const { invitationId } = useParams()
  const current = useCurrentUser()
  const isCandidate = current.status === 'authenticated' && current.user.role === 'candidate'
  const chats = useListMyChats({ query: { refetchInterval: POLL_MS, staleTime: 0 } })

  if (chats.isPending) return <PageLoader />
  if (chats.isError) return <ErrorState message={chats.error.message} />
  const selected = chats.data.find((chat) => chat.invitation_id === invitationId)

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold">Сообщения</h1>
      {chats.data.length === 0 ? (
        <Card className="max-w-3xl">
          <CardHeader>
            <CardTitle>Переписок пока нет</CardTitle>
            <CardDescription>
              {isCandidate
                ? 'Переписка с компанией открывается, когда вы принимаете её приглашение или компания отвечает на ваш отклик.'
                : 'Переписка с кандидатом открывается, когда он принимает ваше приглашение или вы приглашаете к разговору откликнувшегося.'}
            </CardDescription>
          </CardHeader>
        </Card>
      ) : (
        <div className="grid min-h-[60svh] gap-4 md:grid-cols-[320px_1fr]">
          <nav
            aria-label="Переписки"
            className={cn('flex flex-col gap-1', selected && 'max-md:hidden')}
          >
            {chats.data.map((chat) => (
              <ChatListItem
                key={chat.invitation_id}
                chat={chat}
                isCandidate={isCandidate}
                active={chat.invitation_id === invitationId}
              />
            ))}
          </nav>
          {selected ? (
            <Conversation chat={selected} isCandidate={isCandidate} />
          ) : (
            // Ненайденную переписку объясняем и на телефоне, «выберите слева» там лишнее.
            <p
              className={cn(
                'self-center text-center text-sm text-muted-foreground',
                !invitationId && 'max-md:hidden',
              )}
            >
              {invitationId ? 'Переписка не найдена.' : 'Выберите переписку слева.'}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

function chatName(chat: ChatRead, isCandidate: boolean): string {
  if (isCandidate) return chat.company.name
  return chat.candidate_name ?? `Кандидат №${chat.candidate_number}`
}

function ChatListItem({
  chat,
  isCandidate,
  active,
}: {
  chat: ChatRead
  isCandidate: boolean
  active: boolean
}) {
  const last = chat.last_message
  // Компания пишет первой: принятое приглашение без сообщений ждёт её.
  const startHint = !isCandidate && !last && chat.contacts_shared
  return (
    <Link
      to={`/messages/${chat.invitation_id}`}
      aria-current={active ? 'page' : undefined}
      className={cn(
        'flex items-start gap-3 rounded-lg border p-3 transition-colors hover:bg-accent',
        active && 'border-primary bg-accent',
      )}
    >
      {isCandidate ? (
        <CompanyLogo logoUrl={chat.company.logo_url} name={chat.company.name} className="size-10" />
      ) : (
        <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-muted font-mono text-xs">
          №{chat.candidate_number}
        </span>
      )}
      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="flex items-center justify-between gap-2">
          <span className={cn('truncate font-medium', chat.unread > 0 && 'font-semibold')}>
            {chatName(chat, isCandidate)}
          </span>
          {last && (
            <span className="shrink-0 text-xs text-muted-foreground">
              {formatDateTime(last.created_at)}
            </span>
          )}
        </span>
        <span className="truncate text-xs text-muted-foreground">{chat.title}</span>
        <span className="flex items-center justify-between gap-2">
          <span
            className={cn(
              'truncate text-sm',
              startHint ? 'font-medium text-primary' : 'text-muted-foreground',
              chat.unread > 0 && 'text-foreground',
            )}
          >
            {last
              ? `${last.mine ? 'Вы: ' : ''}${last.body}`
              : startHint
                ? 'Принял приглашение: напишите первым'
                : 'Сообщений пока нет'}
          </span>
          <CountBadge count={chat.unread} />
        </span>
      </span>
    </Link>
  )
}

function Conversation({ chat, isCandidate }: { chat: ChatRead; isCandidate: boolean }) {
  return (
    <section className="flex min-w-0 flex-col gap-3 rounded-lg border p-4">
      <header className="flex flex-wrap items-start justify-between gap-2 border-b pb-3">
        <div className="flex min-w-0 flex-col gap-0.5">
          <Link to="/messages" className="text-sm text-primary hover:underline md:hidden">
            ← Все переписки
          </Link>
          <h2 className="truncate font-heading text-lg font-semibold">
            {chatName(chat, isCandidate)}
          </h2>
          <p className="truncate text-sm text-muted-foreground">{chat.title}</p>
        </div>
        <Link
          to={isCandidate ? '/candidate?tab=invitations' : candidatePath(chat.candidate_number)}
          className="text-sm text-primary hover:underline"
        >
          {isCandidate ? 'Приглашение и контакты' : 'Профиль и контакты'}
        </Link>
      </header>
      <ChatPanel
        key={chat.invitation_id}
        invitationId={chat.invitation_id}
        readOnly={!chat.contacts_shared}
        className="max-h-[55svh] min-h-60"
      />
    </section>
  )
}
