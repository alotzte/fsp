import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router'

import {
  getGetMyAssessmentQueryKey,
  useGetMyAssessment,
  useStartAssessmentAttempt,
} from '@/api/generated/assessment/assessment'
import { useListGrades } from '@/api/generated/dictionaries/dictionaries'
import type {
  AssessmentOverviewRead,
  AttemptSummaryRead,
  CategoryRead,
  GradeRead,
} from '@/api/generated/model'
import { ErrorState } from '@/components/error-state'
import { PageLoader } from '@/components/page-loader'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  attemptPath,
  formatDate,
  formatPercent,
  GRADE_HINTS,
  OPTION_STATUS_LABELS,
} from '@/features/assessment/format'
import { useCurrentUser } from '@/features/auth/current-user'
import { cn } from '@/lib/utils'

/** Старт попытки и переход на страницу теста. */
function useStartTest() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  return useStartAssessmentAttempt({
    mutation: {
      onSuccess: (attempt) => {
        // Иначе вернувшийся в кабинет до 30 с видит обзор без «Продолжить тест».
        void queryClient.invalidateQueries({ queryKey: getGetMyAssessmentQueryKey() })
        void navigate(attemptPath(attempt.id))
      },
    },
  })
}

export function AssessmentPanel({
  profileSpecializationId,
}: {
  profileSpecializationId: number | null
}) {
  const overview = useGetMyAssessment()
  const grades = useListGrades()

  if (overview.isPending || grades.isPending) return <PageLoader />
  if (overview.isError) return <ErrorState message={overview.error.message} />
  if (grades.isError) return <ErrorState message={grades.error.message} />

  const { category, active_attempt_id: activeAttemptId, history } = overview.data
  return (
    <div className="grid items-start gap-4 lg:grid-cols-[1fr_320px]">
      <div className="flex flex-col gap-4">
        {activeAttemptId && (
          <Alert>
            <AlertTitle>Тест уже начат</AlertTitle>
            <AlertDescription className="flex flex-wrap items-center justify-between gap-3">
              Время идёт, ответы сохраняются автоматически.
              <Button asChild size="sm">
                <Link to={attemptPath(activeAttemptId)}>Продолжить тест</Link>
              </Button>
            </AlertDescription>
          </Alert>
        )}
        <StartTestCard
          // key: после завершения попытки выбор начинается с актуальной категории.
          key={category ? `${category.specialization.id}-${category.claimed_grade.id}` : 'new'}
          overview={overview.data}
          grades={grades.data}
          profileSpecializationId={profileSpecializationId}
          disabled={activeAttemptId !== null}
        />
      </div>
      <aside className="flex flex-col gap-4 lg:sticky lg:top-4">
        <CategoryCard category={category} disabled={activeAttemptId !== null} />
        {history.length > 0 && <HistoryCard history={history} />}
      </aside>
    </div>
  )
}

function CategoryCard({
  category,
  disabled,
}: {
  category: CategoryRead | null
  disabled: boolean
}) {
  const start = useStartTest()
  const current = useCurrentUser()
  // Песочнице жюри предлагаем экспресс-тест, как основной тест по умолчанию.
  const express = current.status === 'authenticated' && current.user.is_demo
  if (category === null) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Категория</CardTitle>
          <CardDescription>
            Появится после первого теста. По ней работодатели находят кандидатов. Без теста профиль
            виден с пометкой «грейд не подтверждён» и стоит ниже в выдаче.
          </CardDescription>
        </CardHeader>
      </Card>
    )
  }

  const confirmed = category.confirmed_grade
  const offered = category.offered_grade
  return (
    <Card>
      <CardHeader>
        <CardTitle>Категория</CardTitle>
        <CardDescription>Так вас видят работодатели в поиске.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-col gap-2">
          <span className="text-sm text-muted-foreground">{category.specialization.title}</span>
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-heading text-2xl font-semibold">
              {(confirmed ?? category.claimed_grade).title}
            </span>
            {confirmed ? (
              <Badge>подтверждён тестом</Badge>
            ) : (
              <Badge variant="outline">не подтверждён</Badge>
            )}
          </div>
        </div>
        {confirmed && category.next_change_at && (
          <p className="text-sm text-muted-foreground">
            Сменить грейд можно с {formatDate(category.next_change_at)}
          </p>
        )}
        {offered && category.offer_expires_at && (
          <div className="flex flex-col gap-2 rounded-md bg-accent p-3 text-sm">
            <p>
              {confirmed && offered.level > confirmed.level
                ? 'Вы уверенно прошли тест: попробуйте следующий грейд без ожидания.'
                : 'Можно сразу пройти тест на грейд ниже, ограничение по времени не действует.'}
            </p>
            <Button
              size="sm"
              disabled={disabled || start.isPending}
              onClick={() =>
                start.mutate({
                  data: {
                    specialization_id: category.specialization.id,
                    grade_id: offered.id,
                    express,
                  },
                })
              }
            >
              Тест на {offered.title}
            </Button>
            <span className="text-xs text-muted-foreground">
              Предложение действует до {formatDate(category.offer_expires_at)}
            </span>
          </div>
        )}
        {start.isError && (
          <Alert variant="destructive">
            <AlertDescription>{start.error.message}</AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
  )
}

function StartTestCard({
  overview,
  grades,
  profileSpecializationId,
  disabled,
}: {
  overview: AssessmentOverviewRead
  grades: GradeRead[]
  profileSpecializationId: number | null
  disabled: boolean
}) {
  const start = useStartTest()
  const current = useCurrentUser()
  const isDemo = current.status === 'authenticated' && current.user.is_demo
  const [express, setExpress] = useState(isDemo)
  const { tests, options, category } = overview
  // Без истории ФСП подсказки нет, и ФСП здесь не упоминается.
  const suggestedGrade = grades.find((grade) => grade.id === overview.suggested_grade_id)
  const hasTest = (id: number | null | undefined) =>
    id != null && tests.some((test) => test.specialization.id === id)
  const isSelectable = (specId: number | null, gradeId: number) =>
    options.some(
      (o) =>
        o.specialization_id === specId &&
        o.grade_id === gradeId &&
        (o.status === 'available' || o.status === 'offered'),
    )
  const [specializationId, setSpecializationId] = useState<number | null>(
    [category?.specialization.id, profileSpecializationId, tests[0]?.specialization.id].find(
      hasTest,
    ) ?? null,
  )
  // По умолчанию выбран предложенный системой шаг или заявленный грейд, если его можно пройти.
  const [gradeId, setGradeId] = useState<number | null>(
    [category?.offered_grade?.id, category?.claimed_grade.id].find(
      (id) => id != null && isSelectable(specializationId, id),
    ) ?? null,
  )

  if (tests.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Тестирование</CardTitle>
          <CardDescription>Тесты пока не готовы ни для одного направления.</CardDescription>
        </CardHeader>
      </Card>
    )
  }

  const test = tests.find((t) => t.specialization.id === specializationId)
  const optionFor = (id: number) =>
    options.find((o) => o.specialization_id === specializationId && o.grade_id === id)
  const selected = gradeId === null ? undefined : optionFor(gradeId)
  const canStart =
    !disabled &&
    selected !== undefined &&
    (selected.status === 'available' || selected.status === 'offered')

  return (
    <Card>
      <CardHeader>
        <CardTitle>Тест на грейд</CardTitle>
        <CardDescription>
          Выберите направление и грейд, на который претендуете. Задания собираются под вас из банка:
          у каждого кандидата свои, а сложность одинаковая.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        <div className="flex flex-col gap-2">
          <Label htmlFor="assessment-specialization">Направление</Label>
          <Select
            value={specializationId === null ? undefined : String(specializationId)}
            onValueChange={(value) => {
              setSpecializationId(Number(value))
              if (gradeId !== null && !isSelectable(Number(value), gradeId)) setGradeId(null)
            }}
          >
            <SelectTrigger id="assessment-specialization" className="w-full sm:w-80">
              <SelectValue placeholder="Выберите направление" />
            </SelectTrigger>
            <SelectContent>
              {tests.map((t) => (
                <SelectItem key={t.specialization.id} value={String(t.specialization.id)}>
                  {t.specialization.title}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {profileSpecializationId !== null && !hasTest(profileSpecializationId) && (
            <p className="text-sm text-muted-foreground">
              Для направления из вашего профиля тест ещё готовится: пока можно выбрать близкое.
            </p>
          )}
        </div>

        {test && (
          <fieldset className="flex flex-col gap-2">
            <legend className="mb-2 text-sm font-medium">Грейд</legend>
            {suggestedGrade && (
              <p className="mb-1 text-sm text-muted-foreground">
                По вашим результатам ФСП подсказываем {suggestedGrade.title}: выбор за вами. На
                подтверждение грейда подсказка не влияет: его подтверждает только тест.
              </p>
            )}
            {grades.map((grade) => {
              const option = optionFor(grade.id)
              if (!option) return null
              const selectable = option.status === 'available' || option.status === 'offered'
              return (
                <label
                  key={grade.id}
                  className={cn(
                    'flex items-start gap-3 rounded-md border p-3',
                    selectable ? 'cursor-pointer hover:bg-muted/50' : 'opacity-60',
                    gradeId === grade.id && 'border-primary bg-accent',
                  )}
                >
                  <input
                    type="radio"
                    name="grade"
                    className="mt-1 accent-primary"
                    checked={gradeId === grade.id}
                    disabled={!selectable}
                    onChange={() => setGradeId(grade.id)}
                  />
                  <span className="flex flex-1 flex-col gap-1">
                    <span className="flex flex-wrap items-center gap-2 font-medium">
                      {grade.title}
                      {grade.id === suggestedGrade?.id && (
                        <Badge variant="secondary">подсказка ФСП</Badge>
                      )}
                      {option.status !== 'available' && (
                        <Badge variant={option.status === 'offered' ? 'default' : 'outline'}>
                          {OPTION_STATUS_LABELS[option.status]}
                        </Badge>
                      )}
                    </span>
                    <span className="text-sm text-muted-foreground">{GRADE_HINTS[grade.slug]}</span>
                    {option.available_from && (
                      <span className="text-sm text-muted-foreground">
                        Можно пройти с {formatDate(option.available_from)}
                      </span>
                    )}
                  </span>
                </label>
              )
            })}
          </fieldset>
        )}

        {test && (
          <div className="flex flex-col gap-3 rounded-md bg-muted p-4 text-sm">
            <span>
              {express
                ? '6 заданий, 6 минут (экспресс).'
                : `${test.items_count} заданий, ${test.time_limit_minutes} минут.`}{' '}
              Ответы сохраняются сразу, по истечении времени тест завершится сам.
            </span>
            <div className="flex flex-wrap gap-2">
              {test.competencies.map((c) => (
                <Badge key={c.title} variant="secondary">
                  {c.title} · {c.count}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {isDemo && (
          <label className="flex items-start gap-2 text-sm">
            <Checkbox
              className="mt-0.5"
              checked={express}
              onCheckedChange={(checked) => setExpress(checked === true)}
            />
            <span>
              Экспресс-тест для проверки: 6 заданий за 6 минут из тех же компетенций. Точность ниже,
              чем у полного теста, поэтому настоящим кандидатам он недоступен.
            </span>
          </label>
        )}
        {start.isError && (
          <Alert variant="destructive">
            <AlertDescription>{start.error.message}</AlertDescription>
          </Alert>
        )}
        <Button
          className="self-start"
          disabled={!canStart || start.isPending}
          onClick={() =>
            specializationId !== null &&
            gradeId !== null &&
            start.mutate({
              data: { specialization_id: specializationId, grade_id: gradeId, express },
            })
          }
        >
          {start.isPending ? 'Собираем задания...' : 'Начать тест'}
        </Button>
      </CardContent>
    </Card>
  )
}

function HistoryCard({ history }: { history: AttemptSummaryRead[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>История тестов</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="flex flex-col gap-3 text-sm">
          {history.map((attempt) => (
            <li key={attempt.id} className="flex flex-col gap-1">
              <Link to={attemptPath(attempt.id)} className="font-medium hover:underline">
                {attempt.grade.title} · {attempt.specialization.title}
                {attempt.is_express && ' · экспресс'}
              </Link>
              <span className="text-muted-foreground">
                {attempt.finished_at && formatDate(attempt.finished_at)} ·{' '}
                {attempt.passed ? 'подтверждён' : 'не подтверждён'}
                {!attempt.passed &&
                  attempt.estimated_grade &&
                  `, уровень ближе к грейду ${attempt.estimated_grade.title}`}
                {attempt.retest_agreement !== null &&
                  ` · устойчивость ${formatPercent(attempt.retest_agreement)}`}
              </span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}
