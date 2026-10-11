import type { ReactNode } from 'react'

import type { CandidateCategoryRead, EmployerCandidateRead } from '@/api/generated/model'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { formatDate } from '@/features/assessment/format'
import { EmployerViewCard } from '@/features/candidates/employer-view-card'
import { FspResults, FspSportRankLine } from '@/features/fsp/fsp-results'

/** Карточка кандидата для работодателя: профиль, ФСП, кейсы недели, итоги теста. Та же
 * разметка стоит в предпросмотре у кандидата, чтобы он видел ровно то, что увидит работодатель. */
export function CandidateSections({ details }: { details: EmployerCandidateRead }) {
  return (
    <>
      <EmployerViewCard view={details.profile} />
      <Card>
        <CardHeader>
          <CardTitle>Достижения ФСП</CardTitle>
          <CardDescription>
            {details.fsp_results.length > 0 || details.fsp_sport_rank
              ? 'Проверено в реестре Федерации спортивного программирования.'
              : details.fsp_linked
                ? 'ФСП ID привязан, результатов в реестре пока нет.'
                : 'Кандидат не привязал ФСП ID. На позицию в подборке это не влияет.'}
          </CardDescription>
        </CardHeader>
        {(details.fsp_results.length > 0 || details.fsp_sport_rank) && (
          <CardContent className="flex flex-col gap-3">
            {details.fsp_sport_rank && <FspSportRankLine rank={details.fsp_sport_rank} />}
            <FspResults results={details.fsp_results} />
          </CardContent>
        )}
      </Card>
      {details.recent_cases > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Кейсы недели</CardTitle>
            <CardDescription>
              Верно решено за 30 дней: {details.recent_cases}. Короткие задания из банка раз в
              неделю: свежий сигнал, что кандидат в форме; на грейд не влияют.
            </CardDescription>
          </CardHeader>
        </Card>
      )}
      {details.test_results.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Тест на грейд</CardTitle>
            <CardDescription>
              Итоги попытки, подтвердившей грейд. Задания у каждого кандидата свои, сложность
              одинаковая.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col gap-3">
              {details.test_results.map((r) => (
                <li key={r.title} className="flex flex-col gap-1">
                  <span className="flex justify-between text-sm">
                    {r.title}
                    <span className="font-mono">
                      {r.correct}/{r.total}
                    </span>
                  </span>
                  <span className="h-2 overflow-hidden rounded-full bg-muted" aria-hidden>
                    <span
                      className="block h-full bg-primary"
                      style={{ width: `${(100 * r.correct) / r.total}%` }}
                    />
                  </span>
                </li>
              ))}
            </ul>
            {details.foreign_answers > 0 && (
              <p className="mt-3 text-sm text-destructive">
                Ответов от чужого варианта задания: {details.foreign_answers}. Они совпали с
                эталоном другого экземпляра, а не своего, похоже на утечку. Такие ответы не
                засчитаны и на грейд не повлияли.
              </p>
            )}
          </CardContent>
        </Card>
      )}
    </>
  )
}

/** Категория кандидата; children: разбор совпадения с потребностью, если он есть. */
export function CategoryCard({
  category,
  children,
}: {
  category: CandidateCategoryRead
  children?: ReactNode
}) {
  return (
    <Card>
      <CardHeader>
        <CardDescription>
          {category.specialization?.title ?? 'Направление не указано'}
        </CardDescription>
        <CardTitle className="flex flex-wrap items-center gap-2 text-xl">
          {category.grade?.title ?? 'Грейд не указан'}
          {category.confirmed ? (
            <Badge>подтверждён тестом</Badge>
          ) : (
            <Badge variant="outline">не подтверждён</Badge>
          )}
        </CardTitle>
        {category.confirmed_at && (
          <CardDescription>Подтверждён {formatDate(category.confirmed_at)}</CardDescription>
        )}
      </CardHeader>
      {children}
    </Card>
  )
}
