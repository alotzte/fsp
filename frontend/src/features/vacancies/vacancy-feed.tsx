import { useQueryClient } from '@tanstack/react-query'

import { getListMyInvitationsQueryKey } from '@/api/generated/invitations/invitations'
import type { VacancyRead } from '@/api/generated/model'
import {
  getListVacanciesQueryKey,
  useApplyToVacancy,
  useListVacancies,
} from '@/api/generated/vacancies/vacancies'
import { ErrorState } from '@/components/error-state'
import { PageLoader } from '@/components/page-loader'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { WORK_FORMAT_LABELS } from '@/features/candidate-profile/format'
import { CompanyLogo } from '@/features/companies/company-logo'
import { SkillChecks } from '@/features/hiring/match-explanation'
import { formatSalaryRange } from '@/features/invitations/format'
import { InvitationStatusBadge } from '@/features/invitations/status-badge'

/** Лента вакансий своего направления: совпадение с профилем и отклик в одно нажатие. */
export function VacancyFeed() {
  const vacancies = useListVacancies()
  if (vacancies.isPending) return <PageLoader />
  if (vacancies.isError) return <ErrorState message={vacancies.error.message} />
  if (vacancies.data.length === 0) {
    return (
      <Card className="max-w-3xl">
        <CardHeader>
          <CardTitle>Вакансий пока нет</CardTitle>
          <CardDescription>
            Здесь появятся вакансии вашего направления. Основной путь на платформе это приглашения:
            работодатели сами находят кандидатов по категории и подтверждённому грейду.
          </CardDescription>
        </CardHeader>
      </Card>
    )
  }
  return (
    <div className="flex max-w-3xl flex-col gap-4">
      <p className="text-sm text-muted-foreground">
        Отклик сразу открывает компании ваш профиль с ФИО и контактами. С подтверждённым грейдом
        можно откликаться на вакансии своего грейда и соседних, без него до 3 откликов в неделю.
      </p>
      {vacancies.data.map((vacancy) => (
        <VacancyCard key={vacancy.need.id} vacancy={vacancy} />
      ))}
    </div>
  )
}

function VacancyCard({ vacancy }: { vacancy: VacancyRead }) {
  const queryClient = useQueryClient()
  const apply = useApplyToVacancy({
    mutation: {
      onSuccess: () => {
        void queryClient.invalidateQueries({ queryKey: getListVacanciesQueryKey() })
        void queryClient.invalidateQueries({ queryKey: getListMyInvitationsQueryKey() })
      },
    },
  })
  const { need, company } = vacancy
  // Отозванный или истёкший отклик не мешает откликнуться снова.
  const applied =
    vacancy.application_status !== null &&
    vacancy.application_status !== 'withdrawn' &&
    vacancy.application_status !== 'expired'
  const facts = [
    `${need.specialization.title} · ${need.grade.title}`,
    need.city,
    need.work_formats.map((f) => WORK_FORMAT_LABELS[f]).join(', '),
  ].filter(Boolean)

  return (
    <Card>
      <CardHeader className="flex flex-row items-start gap-4">
        <CompanyLogo logoUrl={company.logo_url} name={company.name} />
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <CardDescription className="flex flex-wrap items-center gap-2">
            {company.name}
            {company.verified_domain && (
              <Badge variant="outline">домен {company.verified_domain} подтверждён</Badge>
            )}
          </CardDescription>
          <CardTitle className="text-lg">{need.title}</CardTitle>
          <span className="text-sm text-muted-foreground">{facts.join(' · ')}</span>
        </div>
        {vacancy.application_status && (
          <InvitationStatusBadge status={vacancy.application_status} />
        )}
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <p className="font-heading text-2xl font-semibold">
          {formatSalaryRange(need.salary_from_rub, need.salary_to_rub)}
          <span className="ml-2 text-sm font-normal text-muted-foreground">в месяц</span>
        </p>
        {need.description && (
          <p className="[overflow-wrap:anywhere] whitespace-pre-line">{need.description}</p>
        )}
        <section className="flex flex-col gap-2 rounded-md bg-muted/50 p-3 text-sm">
          <h3 className="font-medium">
            Совпадение с вашим профилем: {Math.round(100 * vacancy.match_score)}%
          </h3>
          <SkillChecks skills={vacancy.skills} />
        </section>
        {applied ? (
          <p className="text-sm text-muted-foreground">
            Вы откликнулись: статус и ответ компании во вкладке «Приглашения».
          </p>
        ) : vacancy.apply_block ? (
          <p className="text-sm text-muted-foreground">{vacancy.apply_block}</p>
        ) : (
          <Button
            className="self-start"
            disabled={apply.isPending}
            onClick={() => apply.mutate({ needId: need.id })}
          >
            Откликнуться
          </Button>
        )}
        {apply.isError && (
          <Alert variant="destructive">
            <AlertDescription>{apply.error.message}</AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
  )
}
