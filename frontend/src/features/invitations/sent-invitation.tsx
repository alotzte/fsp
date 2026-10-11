import { type QueryClient, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router'

import { getGetMyNotificationsQueryKey, getListMyChatsQueryKey } from '@/api/generated/chats/chats'
import {
  getListSentInvitationsQueryKey,
  getSearchCandidatesQueryKey,
  useAnswerApplication,
  useRaiseToCounterOffer,
  useWithdrawInvitation,
} from '@/api/generated/employer/employer'
import type { DeclineReason, EmployerInvitationRead } from '@/api/generated/model'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { formatDate } from '@/features/assessment/format'
import { formatRub } from '@/features/candidate-profile/format'
import { candidatePath } from '@/features/hiring/paths'
import { CaseBlock } from '@/features/invitations/case-block'
import {
  declineReasonLabel,
  EMPLOYER_DECLINE_REASON_LABELS,
  EMPLOYER_DECLINE_REASONS,
  formatSalaryRange,
  isPending,
} from '@/features/invitations/format'
import { InvitationStatusBadge } from '@/features/invitations/status-badge'

export function SentInvitation({ invitation }: { invitation: EmployerInvitationRead }) {
  const isApplication = invitation.direction === 'candidate'
  const queryClient = useQueryClient()
  const withdraw = useWithdrawInvitation({
    mutation: {
      onSuccess: () => refreshEmployerInvitations(queryClient),
    },
  })

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <CardDescription>
            <Link
              to={candidatePath(invitation.candidate_number, invitation.need_id ?? undefined)}
              className="text-primary hover:underline"
            >
              Кандидат №{invitation.candidate_number}
            </Link>
          </CardDescription>
          <CardTitle className="text-lg">{invitation.title}</CardTitle>
        </div>
        <div className="flex flex-wrap gap-2">
          {isApplication && <Badge variant="secondary">отклик на вакансию</Badge>}
          <InvitationStatusBadge status={invitation.status} />
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        <p>
          <span className="font-mono">
            {formatSalaryRange(invitation.salary_from_rub, invitation.salary_to_rub)}
          </span>
          <span className="text-muted-foreground">
            {' '}
            · {isApplication ? 'откликнулся' : 'отправлено'} {formatDate(invitation.created_at)}
            {invitation.viewed_at && ` · просмотрено ${formatDate(invitation.viewed_at)}`}
            {invitation.answered_at && ` · ответ ${formatDate(invitation.answered_at)}`}
            {isPending(invitation.status) && ` · ждём до ${formatDate(invitation.expires_at)}`}
          </span>
        </p>
        {invitation.decline_reason && (
          <p>Причина отказа: {declineReasonLabel(invitation.decline_reason, isApplication)}</p>
        )}
        {isApplication && isPending(invitation.status) && (
          <ApplicationAnswer invitationId={invitation.id} />
        )}
        {!isApplication &&
          isPending(invitation.status) &&
          invitation.counter_salary_rub !== null && (
            <CounterOffer invitationId={invitation.id} salary={invitation.counter_salary_rub} />
          )}
        {invitation.case_task && (
          <CaseBlock
            task={invitation.case_task}
            answer={invitation.case_answer}
            answerTitle="Решение кандидата"
          />
        )}
        <div className="flex flex-wrap gap-2">
          {isPending(invitation.status) && !isApplication && (
            <Button
              variant="outline"
              size="sm"
              disabled={withdraw.isPending}
              onClick={() => withdraw.mutate({ invitationId: invitation.id })}
            >
              Отозвать
            </Button>
          )}
          {invitation.status === 'accepted' && (
            <Button size="sm" asChild>
              <Link to={`/messages/${invitation.id}`}>Открыть переписку</Link>
            </Button>
          )}
          {invitation.status === 'accepted' && invitation.contacts_shared && (
            <Button size="sm" variant="outline" asChild>
              <Link
                to={candidatePath(invitation.candidate_number, invitation.need_id ?? undefined)}
              >
                Контакты кандидата
              </Link>
            </Button>
          )}
        </div>
        {withdraw.isError && (
          <Alert variant="destructive">
            <AlertDescription>{withdraw.error.message}</AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
  )
}

/** Ответ на отклик: пригласить к разговору (открывается переписка) или отказать с причиной. */
function ApplicationAnswer({ invitationId }: { invitationId: string }) {
  const queryClient = useQueryClient()
  const [reason, setReason] = useState<DeclineReason | null>(null)
  const answer = useAnswerApplication({
    mutation: {
      onSuccess: () => refreshEmployerInvitations(queryClient),
    },
  })
  return (
    <div className="flex flex-col gap-2">
      <p className="text-muted-foreground">
        Кандидат откликнулся сам: его профиль и контакты уже открыты.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          disabled={answer.isPending}
          onClick={() => answer.mutate({ invitationId, data: { accept: true } })}
        >
          Пригласить к разговору
        </Button>
        <Select value={reason ?? undefined} onValueChange={(v) => setReason(v as DeclineReason)}>
          <SelectTrigger size="sm" className="w-56" aria-label="Причина отказа">
            <SelectValue placeholder="Причина отказа" />
          </SelectTrigger>
          <SelectContent>
            {EMPLOYER_DECLINE_REASONS.map((r) => (
              <SelectItem key={r} value={r}>
                {EMPLOYER_DECLINE_REASON_LABELS[r]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          size="sm"
          variant="outline"
          disabled={reason === null || answer.isPending}
          onClick={() => reason && answer.mutate({ invitationId, data: { accept: false, reason } })}
        >
          Отказать
        </Button>
      </div>
      {answer.isError && (
        <Alert variant="destructive">
          <AlertDescription>{answer.error.message}</AlertDescription>
        </Alert>
      )}
    </div>
  )
}

/** Встречное предложение кандидата: поднять вилку одним действием или отозвать приглашение. */
function CounterOffer({ invitationId, salary }: { invitationId: string; salary: number }) {
  const queryClient = useQueryClient()
  const raise = useRaiseToCounterOffer({
    mutation: {
      onSuccess: () => refreshEmployerInvitations(queryClient),
    },
  })
  return (
    <div className="flex flex-col gap-2 rounded-md bg-muted/50 p-3">
      <p>
        Кандидат готов рассмотреть предложение при вилке от{' '}
        <span className="font-mono">{formatRub(salary)}</span> до НДФЛ.
      </p>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" disabled={raise.isPending} onClick={() => raise.mutate({ invitationId })}>
          Поднять вилку до {formatRub(salary)}
        </Button>
      </div>
      {raise.isError && (
        <Alert variant="destructive">
          <AlertDescription>{raise.error.message}</AlertDescription>
        </Alert>
      )}
    </div>
  )
}

/** После отзыва, ответа на отклик и подъёма вилки меняются список, бейджи, карточка кандидата
 * и выдача (статус приглашения в ней). */
function refreshEmployerInvitations(queryClient: QueryClient) {
  for (const queryKey of [
    getListSentInvitationsQueryKey(),
    getGetMyNotificationsQueryKey(),
    getListMyChatsQueryKey(),
  ])
    void queryClient.invalidateQueries({ queryKey })
  // Выдача и карточки кандидатов: ключи с параметрами и номером сбрасываем по общему префиксу адреса.
  const [candidatesPrefix] = getSearchCandidatesQueryKey()
  void queryClient.invalidateQueries({
    predicate: (query) => String(query.queryKey[0]).startsWith(String(candidatesPrefix)),
  })
}
