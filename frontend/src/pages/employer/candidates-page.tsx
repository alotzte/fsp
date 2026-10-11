import { useQueryClient } from '@tanstack/react-query'
import { BookmarkCheckIcon, BookmarkPlusIcon } from 'lucide-react'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router'

import {
  getSearchCandidatesQueryKey,
  useAddToShortlist,
  useListHiringNeeds,
  useRemoveFromShortlist,
  useSearchCandidates,
} from '@/api/generated/employer/employer'
import {
  useListGrades,
  useListSkills,
  useListSpecializations,
} from '@/api/generated/dictionaries/dictionaries'
import type { CandidateCardRead, HiringNeedRead, WorkFormat } from '@/api/generated/model'
import { ErrorState } from '@/components/error-state'
import { PageLoader } from '@/components/page-loader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  experienceFact,
  WORK_FORMAT_LABELS,
  WORK_FORMATS,
} from '@/features/candidate-profile/format'
import { SkillsInput } from '@/features/candidate-profile/skills-input'
import { CategoryOverview } from '@/features/hiring/category-overview'
import { matchPercent } from '@/features/hiring/format'
import { MatchExplanation } from '@/features/hiring/match-explanation'
import {
  candidatePath,
  candidatesPath,
  filtersToParams,
  parseCandidateFilters,
  type CandidateFilters,
} from '@/features/hiring/paths'
import { formatSalaryRange } from '@/features/invitations/format'
import { InvitationStatusBadge } from '@/features/invitations/status-badge'

// Radix Select не принимает пустую строку как значение: «любой» кодируем отдельно.
const ANY = 'any'

export function CandidatesPage() {
  const [params, setParams] = useSearchParams()
  const filters = parseCandidateFilters(params)
  const update = (patch: Partial<CandidateFilters>) =>
    setParams(filtersToParams({ ...filters, ...patch }))
  const search = useSearchCandidates({
    need_id: filters.need,
    specialization_id: filters.need ? undefined : filters.specialization,
    grade_id: filters.grade,
    skill_ids: filters.skills,
    confirmed_only: filters.confirmed,
    work_format: filters.format as WorkFormat | undefined,
    has_fsp: filters.fsp,
  })

  return (
    <div className="grid items-start gap-6 lg:grid-cols-[280px_1fr]">
      <Filters filters={filters} onChange={update} />
      <section className="flex flex-col gap-4" aria-label="Подборка">
        {search.isPending && <PageLoader />}
        {search.isError && <ErrorState message={search.error.message} />}
        {search.isSuccess && (
          <>
            <ResultsHeader need={search.data.need} count={search.data.candidates.length} />
            <CategoryOverview
              specializationId={search.data.need?.specialization.id ?? filters.specialization}
              recommendedLevels={
                search.data.need
                  ? [-1, 0, 1].map((shift) => (search.data.need?.grade.level ?? 0) + shift)
                  : undefined
              }
              selectedGradeId={filters.grade}
              onSelect={(category) =>
                update(
                  filters.need
                    ? { grade: category.grade.id }
                    : { specialization: category.specialization.id, grade: category.grade.id },
                )
              }
            />
            {search.data.shortlist.length > 0 && (
              <section className="flex flex-col gap-4" aria-label="Шортлист">
                <h3 className="font-heading text-base font-semibold">
                  Шортлист: {search.data.shortlist.length}
                </h3>
                {search.data.shortlist.map((candidate) => (
                  <CandidateResult
                    key={candidate.candidate_number}
                    candidate={candidate}
                    needId={filters.need}
                  />
                ))}
                <h3 className="font-heading text-base font-semibold">Подборка</h3>
              </section>
            )}
            {search.data.candidates.length === 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>Никого не нашли</CardTitle>
                  <CardDescription>
                    Ослабьте фильтры: уберите часть навыков или разрешите неподтверждённый грейд.
                  </CardDescription>
                </CardHeader>
              </Card>
            )}
            <ResultList
              key={params.toString()}
              candidates={search.data.candidates}
              needId={filters.need}
            />
          </>
        )}
      </section>
    </div>
  )
}

// Ранжируется весь пул сразу (один вызов scoring), поэтому листаем на клиенте.
const PAGE_SIZE = 20

/** Подборка порциями: «Показать ещё» вместо простыни из сотни карточек. Новые фильтры
 * (key по адресу) снова начинают с первой порции. */
function ResultList({ candidates, needId }: { candidates: CandidateCardRead[]; needId?: string }) {
  const [limit, setLimit] = useState(PAGE_SIZE)
  return (
    <>
      {candidates.slice(0, limit).map((candidate) => (
        <CandidateResult key={candidate.candidate_number} candidate={candidate} needId={needId} />
      ))}
      {candidates.length > limit && (
        <Button
          variant="outline"
          className="self-center"
          onClick={() => setLimit(limit + PAGE_SIZE)}
        >
          Показать ещё {Math.min(PAGE_SIZE, candidates.length - limit)} из{' '}
          {candidates.length - limit}
        </Button>
      )}
    </>
  )
}

function ResultsHeader({ need, count }: { need: HiringNeedRead | null; count: number }) {
  return (
    <div className="flex flex-col gap-1">
      <h2 className="text-lg font-semibold">
        {need ? `Подборка: ${need.title}` : 'Поиск по банку кандидатов'}
      </h2>
      <p className="text-sm text-muted-foreground">
        {need
          ? `${need.specialization.title} · ${need.grade.title} и соседние грейды · ${formatSalaryRange(need.salary_from_rub, need.salary_to_rub)}. `
          : 'Кандидаты по силе подтверждённого профиля. '}
        Найдено: {count}. Фильтры сужают подборку, порядок сохраняется.
        {need && ' Отобранные в шортлист остаются наверху при любых фильтрах.'}
      </p>
    </div>
  )
}

function Filters({
  filters,
  onChange,
}: {
  filters: CandidateFilters
  onChange: (patch: Partial<CandidateFilters>) => void
}) {
  const needs = useListHiringNeeds()
  const specializations = useListSpecializations()
  const grades = useListGrades()
  const skills = useListSkills({ kind: 'technology' })
  const selectedSkills = (filters.skills ?? []).map((id) => ({
    skill_id: id,
    title: skills.data?.find((s) => s.id === id)?.title ?? '...',
  }))

  return (
    <Card className="lg:sticky lg:top-4">
      <CardContent className="flex flex-col gap-5 pt-6">
        <div className="flex flex-col gap-2">
          <Label htmlFor="filter-need">Потребность</Label>
          <Select
            value={filters.need ?? ANY}
            onValueChange={(value) => onChange({ need: value === ANY ? undefined : value })}
          >
            <SelectTrigger id="filter-need" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ANY}>Без потребности: весь банк</SelectItem>
              {needs.data?.map((need) => (
                <SelectItem key={need.id} value={need.id}>
                  {need.title}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {!filters.need && (
          <div className="flex flex-col gap-2">
            <Label htmlFor="filter-specialization">Направление</Label>
            <Select
              value={filters.specialization ? String(filters.specialization) : ANY}
              onValueChange={(value) =>
                onChange({ specialization: value === ANY ? undefined : Number(value) })
              }
            >
              <SelectTrigger id="filter-specialization" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ANY}>Любое</SelectItem>
                {specializations.data?.map((s) => (
                  <SelectItem key={s.id} value={String(s.id)}>
                    {s.title}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
        <div className="flex flex-col gap-2">
          <Label htmlFor="filter-grade">Грейд</Label>
          <Select
            value={filters.grade ? String(filters.grade) : ANY}
            onValueChange={(value) =>
              onChange({ grade: value === ANY ? undefined : Number(value) })
            }
          >
            <SelectTrigger id="filter-grade" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ANY}>{filters.need ? 'Как в потребности' : 'Любой'}</SelectItem>
              {grades.data?.map((g) => (
                <SelectItem key={g.id} value={String(g.id)}>
                  {g.title}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <SkillsInput
          kind="technology"
          label="Есть навыки"
          placeholder="Например, Kafka"
          dictionaryOnly
          value={selectedSkills}
          onChange={(value) =>
            onChange({ skills: value.flatMap((s) => (s.skill_id === null ? [] : [s.skill_id])) })
          }
        />
        <div className="flex flex-col gap-2">
          <Label htmlFor="filter-format">Формат работы</Label>
          <Select
            value={filters.format ?? ANY}
            onValueChange={(value) => onChange({ format: value === ANY ? undefined : value })}
          >
            <SelectTrigger id="filter-format" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ANY}>Любой</SelectItem>
              {WORK_FORMATS.map((f) => (
                <SelectItem key={f} value={f}>
                  {WORK_FORMAT_LABELS[f]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <Checkbox
            checked={filters.confirmed ?? false}
            onCheckedChange={(checked) => onChange({ confirmed: checked === true })}
          />
          Только с подтверждённым грейдом
        </label>
        <label className="flex items-center gap-2 text-sm">
          <Checkbox
            checked={filters.fsp ?? false}
            onCheckedChange={(checked) => onChange({ fsp: checked === true })}
          />
          Есть достижения ФСП
        </label>
        <Button variant="ghost" asChild className="self-start">
          <Link to={candidatesPath({ need: filters.need })}>Сбросить фильтры</Link>
        </Button>
      </CardContent>
    </Card>
  )
}

function CandidateResult({ candidate, needId }: { candidate: CandidateCardRead; needId?: string }) {
  const { category, match } = candidate
  const facts = [
    experienceFact(candidate.total_experience_months),
    candidate.city,
    candidate.work_formats.map((f) => WORK_FORMAT_LABELS[f]).join(', '),
  ].filter(Boolean)

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <CardTitle className="text-lg">
            <Link
              to={candidatePath(candidate.candidate_number, needId)}
              className="hover:underline"
            >
              Кандидат №{candidate.candidate_number}
            </Link>
          </CardTitle>
          <CardDescription className="flex flex-wrap items-center gap-2">
            {category.specialization?.title ?? 'Направление не указано'} ·{' '}
            {category.grade?.title ?? 'грейд не указан'}
            {category.confirmed ? (
              <Badge>подтверждён тестом</Badge>
            ) : (
              <Badge variant="outline">не подтверждён</Badge>
            )}
          </CardDescription>
        </div>
        <div className="flex flex-col items-end gap-1">
          <span className="font-heading text-2xl font-semibold">{matchPercent(match)}%</span>
          <span className="text-xs text-muted-foreground">
            {needId ? 'соответствие' : 'сила профиля'}
          </span>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-wrap gap-2">
          {!match.salary_compatible && <Badge variant="destructive">вилка ниже ожиданий</Badge>}
          {!match.format_compatible && <Badge variant="outline">другой формат работы</Badge>}
          {candidate.invitation_status && (
            <InvitationStatusBadge status={candidate.invitation_status} />
          )}
          {candidate.contacts_revealed && <Badge variant="secondary">контакты открыты</Badge>}
          {candidate.recent_cases > 0 && (
            <Badge variant="secondary">кейсы недели: {candidate.recent_cases} за 30 дней</Badge>
          )}
          {candidate.fsp_achievements > 0 && (
            <Badge variant="secondary">ФСП: {candidate.fsp_achievements}</Badge>
          )}
        </div>
        <MatchExplanation match={match} />
        {candidate.technologies.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {candidate.technologies.map((title) => (
              <Badge key={title} variant="outline">
                {title}
              </Badge>
            ))}
          </div>
        )}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-sm text-muted-foreground">{facts.join(' · ')}</span>
          <div className="flex flex-wrap gap-2">
            {needId && (
              <ShortlistButton
                needId={needId}
                candidateNumber={candidate.candidate_number}
                shortlisted={candidate.shortlisted}
              />
            )}
            <Button asChild size="sm">
              <Link to={candidatePath(candidate.candidate_number, needId)}>
                Профиль и приглашение
              </Link>
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function ShortlistButton({
  needId,
  candidateNumber,
  shortlisted,
}: {
  needId: string
  candidateNumber: number
  shortlisted: boolean
}) {
  const queryClient = useQueryClient()
  const mutation = {
    onSuccess: () => queryClient.invalidateQueries({ queryKey: getSearchCandidatesQueryKey() }),
  }
  const add = useAddToShortlist({ mutation })
  const remove = useRemoveFromShortlist({ mutation })
  const pending = add.isPending || remove.isPending
  const variables = { needId, candidateNumber }

  return (
    <Button
      size="sm"
      variant={shortlisted ? 'secondary' : 'outline'}
      disabled={pending}
      onClick={() => (shortlisted ? remove.mutate(variables) : add.mutate(variables))}
    >
      {shortlisted ? <BookmarkCheckIcon /> : <BookmarkPlusIcon />}
      {shortlisted ? 'В шортлисте' : 'В шортлист'}
    </Button>
  )
}
