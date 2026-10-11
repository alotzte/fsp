import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'

import { useGetMyCompany } from '@/api/generated/companies/companies'
import {
  getDownloadEmployerCandidatePdfUrl,
  getGetEmployerCandidateQueryKey,
  getListSentInvitationsQueryKey,
  getSearchCandidatesQueryKey,
  useGetEmployerCandidate,
  useGetHiringNeed,
  useSendInvitation,
} from '@/api/generated/employer/employer'
import type { EmployerCandidateRead, HiringNeedRead } from '@/api/generated/model'
import { DownloadPdfButton } from '@/components/download-pdf-button'
import { ErrorState } from '@/components/error-state'
import { PageLoader } from '@/components/page-loader'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { formatDate } from '@/features/assessment/format'
import { CandidateSections, CategoryCard } from '@/features/candidates/candidate-sections'
import { matchPercent } from '@/features/hiring/format'
import { MatchExplanation } from '@/features/hiring/match-explanation'
import { candidatesPath } from '@/features/hiring/paths'
import { CaseBlock } from '@/features/invitations/case-block'
import {
  declineReasonLabel,
  formatSalaryRange,
  isPending,
  parseRub,
} from '@/features/invitations/format'
import { InvitationStatusBadge } from '@/features/invitations/status-badge'

export function EmployerCandidatePage() {
  const { candidateNumber = '' } = useParams()
  const [params] = useSearchParams()
  const needId = params.get('need') ?? undefined
  const candidate = useGetEmployerCandidate(Number(candidateNumber), { need_id: needId })

  return (
    <div className="flex flex-col gap-4">
      <Link to={candidatesPath({ need: needId })} className="text-sm text-primary hover:underline">
        ← К подборке
      </Link>
      {candidate.isPending && <PageLoader />}
      {candidate.isError && <ErrorState message={candidate.error.message} />}
      {candidate.isSuccess && <CandidateDetails details={candidate.data} needId={needId} />}
    </div>
  )
}

function CandidateDetails({
  details,
  needId,
}: {
  details: EmployerCandidateRead
  needId?: string
}) {
  const { category, match, contacts } = details
  const pendingInvitation = details.invitations.find((i) => isPending(i.status))
  // Приглашения отсортированы от новых к старым: после принятия контакт уже установлен. Если
  // кандидат потом закрыл доступ, вернуть его можно только новым приглашением: форма нужна.
  const accepted = details.invitations[0]?.status === 'accepted' && contacts !== null

  return (
    <div className="grid items-start gap-4 lg:grid-cols-[1fr_380px]">
      <div className="flex flex-col gap-4">
        <div>
          <DownloadPdfButton
            apiPath={getDownloadEmployerCandidatePdfUrl(details.profile.candidate_number)}
          />
        </div>
        <CandidateSections details={details} />
      </div>

      <aside className="flex flex-col gap-4 lg:sticky lg:top-4">
        <CategoryCard category={category}>
          {match && (
            <CardContent className="flex flex-col gap-3">
              <p className="text-sm">
                Соответствие потребности:{' '}
                <span className="font-heading text-lg font-semibold">{matchPercent(match)}%</span>
              </p>
              <MatchExplanation match={match} detailed />
            </CardContent>
          )}
        </CategoryCard>

        <Card>
          <CardHeader>
            <CardTitle>Контакты</CardTitle>
            {!contacts && (
              <CardDescription>Откроются, когда кандидат примет ваше приглашение.</CardDescription>
            )}
          </CardHeader>
          {contacts && (
            <CardContent>
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
                <dt className="text-muted-foreground">ФИО</dt>
                <dd>{[contacts.last_name, contacts.first_name, contacts.middle_name].join(' ')}</dd>
                <dt className="text-muted-foreground">Email</dt>
                <dd>
                  <a href={`mailto:${contacts.email}`} className="text-primary hover:underline">
                    {contacts.email}
                  </a>
                </dd>
                {contacts.phone && (
                  <>
                    <dt className="text-muted-foreground">Телефон</dt>
                    <dd>{contacts.phone}</dd>
                  </>
                )}
                {contacts.telegram && (
                  <>
                    <dt className="text-muted-foreground">Telegram</dt>
                    <dd>@{contacts.telegram}</dd>
                  </>
                )}
              </dl>
            </CardContent>
          )}
        </Card>

        {accepted ? null : pendingInvitation ? (
          <Alert>
            <AlertDescription>
              Приглашение отправлено {formatDate(pendingInvitation.created_at)}, ждём ответа до{' '}
              {formatDate(pendingInvitation.expires_at)}
            </AlertDescription>
          </Alert>
        ) : (
          <InviteForm
            candidateNumber={details.profile.candidate_number}
            needId={needId}
            salaryCompatible={match?.salary_compatible ?? true}
          />
        )}

        {details.invitations.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle>Приглашения</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              {details.invitations.map((invitation) => (
                <div key={invitation.id} className="flex flex-col gap-2 text-sm">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-medium">{invitation.title}</span>
                    <InvitationStatusBadge status={invitation.status} />
                  </div>
                  <span className="text-muted-foreground">
                    {formatSalaryRange(invitation.salary_from_rub, invitation.salary_to_rub)} ·{' '}
                    {formatDate(invitation.created_at)}
                    {invitation.decline_reason &&
                      ` · ${declineReasonLabel(invitation.decline_reason, invitation.direction === 'candidate')}`}
                  </span>
                  {invitation.case_task && (
                    <CaseBlock
                      task={invitation.case_task}
                      answer={invitation.case_answer}
                      answerTitle="Решение кандидата"
                    />
                  )}
                  {invitation.status === 'accepted' && (
                    <Button size="sm" asChild className="self-start">
                      <Link to={`/messages/${invitation.id}`}>Открыть переписку</Link>
                    </Button>
                  )}
                </div>
              ))}
            </CardContent>
          </Card>
        )}
      </aside>
    </div>
  )
}

function InviteForm(props: {
  candidateNumber: number
  needId?: string
  salaryCompatible: boolean
}) {
  const need = useGetHiringNeed(props.needId ?? '', { query: { enabled: !!props.needId } })
  const company = useGetMyCompany()
  if ((props.needId && need.isPending) || company.isPending) return <PageLoader />
  return (
    <InviteFormFields
      {...props}
      need={need.data}
      defaultContact={company.data?.contact_email || company.data?.contact_phone || ''}
    />
  )
}

function InviteFormFields({
  candidateNumber,
  needId,
  salaryCompatible,
  need,
  defaultContact,
}: {
  candidateNumber: number
  needId?: string
  salaryCompatible: boolean
  need?: HiringNeedRead
  defaultContact: string
}) {
  const queryClient = useQueryClient()
  const [title, setTitle] = useState(need?.title ?? '')
  const [description, setDescription] = useState(need?.description ?? '')
  const [salaryFrom, setSalaryFrom] = useState(need ? String(need.salary_from_rub) : '')
  const [salaryTo, setSalaryTo] = useState(need ? String(need.salary_to_rub) : '')
  const [contact, setContact] = useState(defaultContact)
  const [caseTask, setCaseTask] = useState('')
  const send = useSendInvitation({
    mutation: {
      onSuccess: () => {
        void queryClient.invalidateQueries({
          queryKey: getGetEmployerCandidateQueryKey(candidateNumber),
        })
        void queryClient.invalidateQueries({ queryKey: getListSentInvitationsQueryKey() })
        void queryClient.invalidateQueries({ queryKey: getSearchCandidatesQueryKey() })
      },
    },
  })
  const fromRub = parseRub(salaryFrom)
  const toRub = parseRub(salaryTo)
  // Подсказка вместо молча неактивной кнопки: «200 000» принимаем, а копейки и «1e6» нет.
  const salaryError =
    (salaryFrom.trim() && fromRub === null) || (salaryTo.trim() && toRub === null)
      ? 'Сумма в рублях, без копеек, до 10 000 000'
      : fromRub !== null && toRub !== null && toRub < fromRub
        ? 'Верх вилки не может быть меньше нижней границы'
        : null
  const complete =
    title.trim() &&
    description.trim() &&
    contact.trim() &&
    fromRub !== null &&
    toRub !== null &&
    !salaryError

  return (
    <Card>
      <CardHeader>
        <CardTitle>Пригласить</CardTitle>
        <CardDescription>
          Кандидат увидит компанию, предложение и вилку сразу. Контакты кандидата откроются, когда
          он примет приглашение.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form
          className="flex flex-col gap-3"
          onSubmit={(event) => {
            event.preventDefault()
            send.mutate({
              data: {
                candidate_number: candidateNumber,
                need_id: needId ?? null,
                title: title.trim(),
                description: description.trim(),
                salary_from_rub: fromRub ?? 0,
                salary_to_rub: toRub ?? 0,
                contact: contact.trim(),
                case_task: caseTask.trim(),
              },
            })
          }}
        >
          <div className="flex flex-col gap-2">
            <Label htmlFor="invite-title">Должность</Label>
            <Input
              id="invite-title"
              maxLength={200}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="invite-description">Предложение</Label>
            <Textarea
              id="invite-description"
              rows={4}
              maxLength={3000}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-2">
              <Label htmlFor="invite-from">От, ₽ до НДФЛ</Label>
              <Input
                id="invite-from"
                inputMode="numeric"
                value={salaryFrom}
                onChange={(e) => setSalaryFrom(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="invite-to">До, ₽ до НДФЛ</Label>
              <Input
                id="invite-to"
                inputMode="numeric"
                value={salaryTo}
                onChange={(e) => setSalaryTo(e.target.value)}
              />
            </div>
          </div>
          {salaryError && <p className="text-sm text-destructive">{salaryError}</p>}
          <div className="flex flex-col gap-2">
            <Label htmlFor="invite-contact">Как с вами связаться</Label>
            <Input
              id="invite-contact"
              maxLength={300}
              placeholder="email, телефон или Telegram рекрутера"
              value={contact}
              onChange={(e) => setContact(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="invite-case">Кейс (необязательно)</Label>
            <Textarea
              id="invite-case"
              rows={3}
              maxLength={1500}
              value={caseTask}
              placeholder="Например: как бы вы спроектировали повторную отправку платежа?"
              onChange={(e) => setCaseTask(e.target.value)}
            />
            <span className="text-xs text-muted-foreground">
              Короткий вопрос о подходе, не реальная задача. Кандидат ответит при принятии, и вы
              увидите решение вместе с его контактами.
            </span>
          </div>
          {!salaryCompatible && (
            <Alert variant="destructive">
              <AlertDescription>
                Верх вилки потребности ниже ожиданий кандидата: поднимите его, иначе приглашение не
                отправится.
              </AlertDescription>
            </Alert>
          )}
          {send.isError && (
            <Alert variant="destructive">
              <AlertDescription>{send.error.message}</AlertDescription>
            </Alert>
          )}
          {send.isSuccess ? (
            <Alert>
              <AlertDescription>Приглашение отправлено.</AlertDescription>
            </Alert>
          ) : (
            <Button type="submit" disabled={!complete || send.isPending}>
              Отправить приглашение
            </Button>
          )}
        </form>
      </CardContent>
    </Card>
  )
}
