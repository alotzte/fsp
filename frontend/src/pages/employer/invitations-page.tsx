import { useListSentInvitations } from '@/api/generated/employer/employer'
import type { EmployerInvitationRead } from '@/api/generated/model'
import { ErrorState } from '@/components/error-state'
import { PageLoader } from '@/components/page-loader'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { isPending } from '@/features/invitations/format'
import { SentInvitation } from '@/features/invitations/sent-invitation'

// Ответы кандидатов появляются без перезагрузки.
const POLL_MS = 15_000

/** Ждёт решения компании: отклик кандидата или его встречное предложение по вилке. */
function awaitsCompany(i: EmployerInvitationRead): boolean {
  return isPending(i.status) && (i.direction === 'candidate' || i.counter_salary_rub !== null)
}

const GROUPS: { title: string; hint?: string; test: (i: EmployerInvitationRead) => boolean }[] = [
  { title: 'Ждут вашего ответа', test: awaitsCompany },
  {
    title: 'Приняли: контакты и переписка открыты',
    test: (i) => i.status === 'accepted',
  },
  {
    title: 'Ждут ответа кандидата',
    hint: 'Ответ кандидата освобождает место для нового приглашения.',
    test: (i) => isPending(i.status) && !awaitsCompany(i),
  },
  {
    title: 'Завершённые',
    test: (i) => !isPending(i.status) && i.status !== 'accepted',
  },
]

export function InvitationsPage() {
  const invitations = useListSentInvitations({ query: { refetchInterval: POLL_MS } })

  if (invitations.isPending) return <PageLoader />
  if (invitations.isError) return <ErrorState message={invitations.error.message} />
  const items = invitations.data

  if (items.length === 0) {
    return (
      <Card className="max-w-4xl">
        <CardHeader>
          <CardTitle>Приглашений пока нет</CardTitle>
          <CardDescription>
            Откройте подборку по потребности и пригласите подходящих кандидатов.
          </CardDescription>
        </CardHeader>
      </Card>
    )
  }
  return (
    <div className="flex max-w-4xl flex-col gap-8">
      {GROUPS.map((group) => {
        const groupItems = items.filter(group.test)
        if (groupItems.length === 0) return null
        return (
          <section key={group.title} className="flex flex-col gap-4" aria-label={group.title}>
            <div className="flex flex-col gap-1">
              <h2 className="font-heading text-lg font-semibold">
                {group.title}: {groupItems.length}
              </h2>
              {group.hint && <p className="text-sm text-muted-foreground">{group.hint}</p>}
            </div>
            {groupItems.map((invitation) => (
              <SentInvitation key={invitation.id} invitation={invitation} />
            ))}
          </section>
        )
      })}
    </div>
  )
}
