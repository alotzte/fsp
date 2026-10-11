import { getGetMyNotificationsQueryKey, getListMyChatsQueryKey } from '@/api/generated/chats/chats'
import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router'

import {
  getListMyInvitationsQueryKey,
  useAcceptInvitation,
  useCounterInvitation,
  useDeclineInvitation,
  useListMyInvitations,
  useReportCompany,
  useRevokeContactAccess,
  useWithdrawApplication,
} from '@/api/generated/invitations/invitations'
import type {
  CandidateInvitationRead,
  CompanyReputationRead,
  DeclineReason,
  InvitationMatchRead,
  ReportReason,
} from '@/api/generated/model'
import { ErrorState } from '@/components/error-state'
import { PageLoader } from '@/components/page-loader'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { formatDate } from '@/features/assessment/format'
import { formatRub } from '@/features/candidate-profile/format'
import { CompanyLogo } from '@/features/companies/company-logo'
import { SkillChecks } from '@/features/hiring/match-explanation'
import { CaseBlock } from '@/features/invitations/case-block'
import {
  DECLINE_REASON_LABELS,
  DECLINE_REASONS,
  declineReasonLabel,
  formatSalaryRange,
  isPending,
  REPORT_REASON_LABELS,
  REPORT_REASONS,
  parseRub,
} from '@/features/invitations/format'
import { InvitationStatusBadge } from '@/features/invitations/status-badge'

const POLL_MS = 15_000

/** Входящие приглашения. Открытие списка отмечает новые приглашения просмотренными. */
export function CandidateInvitations() {
  // Новые приглашения и ответы компаний появляются без перезагрузки.
  const invitations = useListMyInvitations({ query: { refetchInterval: POLL_MS } })

  if (invitations.isPending) return <PageLoader />
  if (invitations.isError) return <ErrorState message={invitations.error.message} />
  if (invitations.data.length === 0) {
    return (
      <Card className="max-w-3xl">
        <CardHeader>
          <CardTitle>Приглашений и откликов пока нет</CardTitle>
          <CardDescription>
            Работодатели находят кандидатов по категории (направлению и подтверждённому грейду) и
            сами присылают предложения с вилкой зарплаты. Пройдите тест и включите показ профиля,
            чтобы попасть в подборки. Откликнуться самому можно на вкладке «Вакансии».
          </CardDescription>
        </CardHeader>
      </Card>
    )
  }
  // Сначала то, что ждёт ответа кандидата, чтобы это не пряталось ниже прокрутки.
  const toAnswer = invitations.data.filter(awaitsMyAnswer)
  const rest = invitations.data.filter((i) => !awaitsMyAnswer(i))
  return (
    <div className="flex max-w-3xl flex-col gap-4">
      {toAnswer.length > 0 && (
        <h2 className="font-heading text-lg font-semibold">
          Ждут вашего ответа: {toAnswer.length}
        </h2>
      )}
      {toAnswer.map((invitation) => (
        <InvitationCard key={invitation.id} invitation={invitation} />
      ))}
      {toAnswer.length > 0 && rest.length > 0 && (
        <h2 className="mt-4 font-heading text-lg font-semibold">Остальные</h2>
      )}
      {rest.map((invitation) => (
        <InvitationCard key={invitation.id} invitation={invitation} />
      ))}
    </div>
  )
}

/** Приглашение компании без ответа кандидата (встречное предложение уже считается ответом). */
function awaitsMyAnswer(invitation: CandidateInvitationRead): boolean {
  return (
    invitation.direction === 'employer' &&
    isPending(invitation.status) &&
    invitation.counter_salary_rub === null
  )
}

function InvitationCard({ invitation }: { invitation: CandidateInvitationRead }) {
  const queryClient = useQueryClient()
  // Ответ на приглашение меняет и бейджи в шапке, и список переписок, а не только этот список.
  const refresh = () => {
    for (const queryKey of [
      getListMyInvitationsQueryKey(),
      getGetMyNotificationsQueryKey(),
      getListMyChatsQueryKey(),
    ])
      void queryClient.invalidateQueries({ queryKey })
  }
  const accept = useAcceptInvitation({ mutation: { onSuccess: refresh } })
  const decline = useDeclineInvitation({ mutation: { onSuccess: refresh } })
  const counter = useCounterInvitation({ mutation: { onSuccess: refresh } })
  const [counterSalary, setCounterSalary] = useState('')
  const revoke = useRevokeContactAccess({ mutation: { onSuccess: refresh } })
  const withdraw = useWithdrawApplication({ mutation: { onSuccess: refresh } })
  // Свой отклик на вакансию: на него отвечает компания, кандидат может только отозвать.
  const isApplication = invitation.direction === 'candidate'
  const [reason, setReason] = useState<DeclineReason | null>(null)
  const [caseAnswer, setCaseAnswer] = useState('')
  const { company } = invitation
  const pending = isPending(invitation.status)
  const error = accept.error ?? decline.error ?? revoke.error ?? withdraw.error ?? counter.error

  return (
    <Card>
      <CardHeader className="flex flex-row items-start gap-4">
        <CompanyLogo logoUrl={company.logo_url} name={company.name} />
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <CardDescription className="flex flex-wrap items-center gap-2">
            {company.name}
            {isApplication && ' · ваш отклик'}
            {company.verified_domain && (
              <Badge variant="outline">домен {company.verified_domain} подтверждён</Badge>
            )}
          </CardDescription>
          <CardTitle className="text-lg">{invitation.title}</CardTitle>
        </div>
        <div className="flex flex-col items-end gap-1">
          <InvitationStatusBadge status={invitation.status} />
          {invitation.case_task && !invitation.case_answer && pending && (
            <Badge variant="secondary">есть кейс</Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <p className="font-heading text-2xl font-semibold">
          {formatSalaryRange(invitation.salary_from_rub, invitation.salary_to_rub)}
          <span className="ml-2 text-sm font-normal text-muted-foreground">в месяц</span>
        </p>
        {pending && isApplication && (
          <div className="flex flex-col items-start gap-2 text-sm">
            <p className="text-muted-foreground">
              Компания уже видит ваш профиль с ФИО и контактами. Если пригласит к разговору,
              откроется переписка.
            </p>
            <Button
              variant="outline"
              size="sm"
              disabled={withdraw.isPending}
              onClick={() => withdraw.mutate({ invitationId: invitation.id })}
            >
              Отозвать отклик
            </Button>
          </div>
        )}

        {invitation.case_task &&
          (pending && !isApplication ? (
            <section className="flex flex-col gap-2 rounded-md border-2 border-primary bg-accent/40 p-4 text-sm">
              <h3 className="font-heading text-base font-semibold">Компания просит решить кейс</h3>
              <p className="[overflow-wrap:anywhere] whitespace-pre-line">{invitation.case_task}</p>
              <Label htmlFor={`case-${invitation.id}`}>Ваше решение</Label>
              <Textarea
                id={`case-${invitation.id}`}
                rows={4}
                maxLength={3000}
                value={caseAnswer}
                className="bg-background"
                placeholder="Опишите подход в нескольких предложениях"
                onChange={(event) => setCaseAnswer(event.target.value)}
              />
              <span className="text-xs text-muted-foreground">
                Решение уйдёт вместе с принятием приглашения: компания увидит его вместе с вашими
                контактами. Можно принять и без решения.
              </span>
            </section>
          ) : (
            <CaseBlock
              task={invitation.case_task}
              answer={invitation.case_answer}
              answerTitle="Ваше решение"
            />
          ))}

        {pending && !isApplication && (
          <div className="flex flex-wrap items-center gap-2">
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button disabled={accept.isPending}>Принять</Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Принять приглашение?</AlertDialogTitle>
                  <AlertDialogDescription>
                    Компания «{company.name}» увидит ваши ФИО, email, телефон и Telegram, и
                    откроется переписка. Доступ к контактам можно закрыть в любой момент.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                {invitation.case_task && (
                  <p className="text-sm">
                    {caseAnswer.trim()
                      ? 'Решение кейса отправится вместе с принятием.'
                      : 'Вы не ответили на кейс, компания увидит только контакты. Решение можно написать в карточке выше.'}
                  </p>
                )}
                <AlertDialogFooter>
                  <AlertDialogCancel>Отмена</AlertDialogCancel>
                  <AlertDialogAction
                    onClick={() =>
                      accept.mutate({
                        invitationId: invitation.id,
                        data: caseAnswer.trim() ? { case_answer: caseAnswer.trim() } : undefined,
                      })
                    }
                  >
                    Принять и открыть контакты
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
            <Select
              value={reason ?? undefined}
              onValueChange={(v) => setReason(v as DeclineReason)}
            >
              <SelectTrigger className="w-60" aria-label="Причина отказа">
                <SelectValue placeholder="Причина отказа" />
              </SelectTrigger>
              <SelectContent>
                {DECLINE_REASONS.map((r) => (
                  <SelectItem key={r} value={r}>
                    {DECLINE_REASON_LABELS[r]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              variant="outline"
              disabled={reason === null || decline.isPending}
              onClick={() =>
                reason && decline.mutate({ invitationId: invitation.id, data: { reason } })
              }
            >
              Отклонить
            </Button>
          </div>
        )}

        {pending && !isApplication && invitation.counter_salary_rub !== null && (
          <p className="text-sm text-muted-foreground">
            Вы ответили, что готовы при вилке от {formatRub(invitation.counter_salary_rub)} до НДФЛ.
            Ждём решения компании: если она поднимет вилку, приглашение обновится.
          </p>
        )}
        {pending && !isApplication && invitation.counter_salary_rub === null && (
          <form
            className="flex flex-wrap items-center gap-2 text-sm"
            onSubmit={(event) => {
              event.preventDefault()
              counter.mutate({
                invitationId: invitation.id,
                data: { salary_rub: parseRub(counterSalary) ?? 0 },
              })
            }}
          >
            <span className="text-muted-foreground">Не хватает зарплаты? Готов при вилке от</span>
            <Input
              className="w-32"
              inputMode="numeric"
              aria-label="Готов при вилке от, ₽ до вычета НДФЛ"
              placeholder={String(invitation.salary_to_rub + 50_000)}
              value={counterSalary}
              onChange={(event) => setCounterSalary(event.target.value.replace(/\D/g, ''))}
            />
            <Button
              type="submit"
              size="sm"
              variant="outline"
              disabled={parseRub(counterSalary) === null || counter.isPending}
            >
              Предложить
            </Button>
            {counterSalary && parseRub(counterSalary) === null && (
              <span className="w-full text-xs text-destructive">Не больше 10 000 000 ₽</span>
            )}
            <span className="w-full text-xs text-muted-foreground">
              Контакты при этом не раскрываются, а сумму компания узнает только эту.
            </span>
          </form>
        )}

        {/* Контакты открывает и отклик: закрыть их можно в любом статусе, а не только у принятых. */}
        {(invitation.status === 'accepted' || invitation.contacts_shared) && (
          <section className="flex flex-col gap-3 border-t pt-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              {invitation.contacts_shared ? (
                <Badge>компания видит ваши контакты</Badge>
              ) : (
                <Badge variant="outline">доступ к контактам закрыт</Badge>
              )}
              {invitation.contacts_shared && (
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button variant="ghost" size="sm" disabled={revoke.isPending}>
                      Закрыть доступ к контактам
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>Закрыть доступ к контактам?</AlertDialogTitle>
                      <AlertDialogDescription>
                        Компания «{company.name}» перестанет видеть ваши ФИО и контакты, а переписка
                        станет только для чтения у обеих сторон. Открыть доступ снова можно, только
                        приняв новое приглашение этой компании.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Отмена</AlertDialogCancel>
                      <AlertDialogAction onClick={() => revoke.mutate({ companyId: company.id })}>
                        Закрыть доступ
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              )}
            </div>
            {invitation.status === 'accepted' && (
              <Button asChild className="self-start">
                <Link to={`/messages/${invitation.id}`}>Открыть переписку</Link>
              </Button>
            )}
          </section>
        )}

        <p className="border-t pt-4 [overflow-wrap:anywhere] whitespace-pre-line">
          {invitation.description}
        </p>
        <CompanyReputation reputation={company.reputation} />
        {invitation.match && (
          <WhyYou
            match={invitation.match}
            title={isApplication ? 'Ваше совпадение с вакансией' : 'Почему вам предложили'}
          />
        )}
        <dl className="grid gap-1 text-sm sm:grid-cols-[auto_1fr] sm:gap-x-4">
          <dt className="text-muted-foreground">Связь</dt>
          <dd>{invitation.contact}</dd>
          {company.website && (
            <>
              <dt className="text-muted-foreground">Сайт</dt>
              <dd>
                <a href={company.website} className="text-primary hover:underline">
                  {company.website}
                </a>
              </dd>
            </>
          )}
          {pending && (
            <>
              <dt className="text-muted-foreground">
                {isApplication ? 'Компания ответит до' : 'Ответить до'}
              </dt>
              <dd>{formatDate(invitation.expires_at)}</dd>
            </>
          )}
          {invitation.decline_reason && (
            <>
              <dt className="text-muted-foreground">Причина отказа</dt>
              <dd>{declineReasonLabel(invitation.decline_reason, isApplication)}</dd>
            </>
          )}
        </dl>

        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error.message}</AlertDescription>
          </Alert>
        )}

        {!isApplication && <ReportCompany invitation={invitation} onReported={refresh} />}
      </CardContent>
    </Card>
  )
}

/** Жалоба на компанию: несколько жалоб разных кандидатов замораживают её до разбора. */
function ReportCompany({
  invitation,
  onReported,
}: {
  invitation: CandidateInvitationRead
  onReported: () => void
}) {
  const [reason, setReason] = useState<ReportReason | null>(null)
  const report = useReportCompany({ mutation: { onSuccess: onReported } })
  if (invitation.reported) {
    return (
      <p className="text-xs text-muted-foreground">
        Вы пожаловались на компанию. Спасибо, жалобы разбирают администраторы платформы.
      </p>
    )
  }
  return (
    <details className="text-sm">
      <summary className="cursor-pointer text-muted-foreground">Пожаловаться на компанию</summary>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <Select value={reason ?? undefined} onValueChange={(v) => setReason(v as ReportReason)}>
          <SelectTrigger size="sm" className="w-72" aria-label="Причина жалобы">
            <SelectValue placeholder="Что не так" />
          </SelectTrigger>
          <SelectContent>
            {REPORT_REASONS.map((r) => (
              <SelectItem key={r} value={r}>
                {REPORT_REASON_LABELS[r]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          size="sm"
          variant="outline"
          disabled={reason === null || report.isPending}
          onClick={() => reason && report.mutate({ invitationId: invitation.id, data: { reason } })}
        >
          Отправить жалобу
        </Button>
      </div>
      {report.isError && (
        <Alert variant="destructive" className="mt-2">
          <AlertDescription>{report.error.message}</AlertDescription>
        </Alert>
      )}
    </details>
  )
}

/** Почему компания написала именно вам: снимок совпадения на момент отправки приглашения. */
function WhyYou({ match, title }: { match: InvitationMatchRead; title: string }) {
  return (
    <section className="flex flex-col gap-2 rounded-md bg-muted/50 p-3 text-sm">
      <h3 className="font-medium">{title}</h3>
      <p>Совпадение с потребностью компании: {Math.round(100 * match.score)}%</p>
      <SkillChecks skills={match.skills} />
      <ul className="flex flex-col gap-1">
        {match.grade && (
          <li>
            Грейд {match.grade}{' '}
            {match.grade_confirmed ? 'подтверждён тестом' : 'заявлен, тестом пока не подтверждён'}
          </li>
        )}
        {match.fsp_achievements > 0 && <li>Достижения ФСП: {match.fsp_achievements}</li>}
      </ul>
    </section>
  )
}

/** 30.5 часа → «через 31 ч», 50 часов → «через 2 дн.». */
function formatReplyTime(hours: number): string {
  if (hours < 1) return 'меньше чем через час'
  if (hours < 48) return `через ${Math.round(hours)} ч`
  return `через ${Math.round(hours / 24)} дн.`
}

/** Как компания ведёт себя с кандидатами. Считаем по её завершённым приглашениям, а не по анкете. */
function CompanyReputation({ reputation }: { reputation: CompanyReputationRead | null }) {
  if (!reputation) {
    return (
      <p className="text-sm text-muted-foreground">
        О том, как компания ведёт себя с кандидатами, пока мало данных.
      </p>
    )
  }
  return (
    <section className="flex flex-col gap-1 text-sm" aria-label="Репутация компании">
      <h3 className="font-medium">
        Компания после принятия приглашения{' '}
        <span className="font-normal text-muted-foreground">
          (по {reputation.invitations} приглашениям)
        </span>
      </h3>
      <ul className="flex flex-col gap-1">
        {reputation.replied_share !== null && (
          <li>
            Пишет кандидату в течение 3 дней: {Math.round(100 * reputation.replied_share)}%
            {reputation.median_reply_hours !== null &&
              `, обычно ${formatReplyTime(reputation.median_reply_hours)}`}
          </li>
        )}
        <li>Отзывает приглашения: {Math.round(100 * reputation.withdrawn_share)}%</li>
      </ul>
    </section>
  )
}
