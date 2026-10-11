import { useListCandidateCategories } from '@/api/generated/employer/employer'
import type { CategoryCountRead, GradeRead } from '@/api/generated/model'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'

type GradedCategory = CategoryCountRead & { grade: GradeRead }

/** Категории банка «направление × грейд» по результатам теста: откуда начинать поиск.
 * С потребностью: только её грейд и соседние (рекомендованные). Клик ставит фильтр. */
export function CategoryOverview({
  specializationId,
  recommendedLevels,
  selectedGradeId,
  onSelect,
}: {
  specializationId?: number
  recommendedLevels?: number[]
  selectedGradeId?: number
  onSelect: (category: GradedCategory) => void
}) {
  const categories = useListCandidateCategories()
  if (!categories.isSuccess) return null
  const shown = categories.data.filter(
    (c) => !specializationId || c.specialization.id === specializationId,
  )
  // Бэкенд отдаёт категории по порядку направлений: группируем подряд идущие.
  const groups = new Map<number, CategoryCountRead[]>()
  for (const c of shown) {
    groups.set(c.specialization.id, [...(groups.get(c.specialization.id) ?? []), c])
  }
  if (groups.size === 0) return null

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          {recommendedLevels ? 'Рекомендованные категории' : 'Категории банка'}
        </CardTitle>
        <CardDescription>
          Направление × грейд по результатам теста. Нажмите на категорию, чтобы отфильтровать
          подборку.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {[...groups.values()].map((items) => {
          const graded = items.filter(
            (c): c is GradedCategory =>
              c.grade !== null && (!recommendedLevels || recommendedLevels.includes(c.grade.level)),
          )
          const untested = items.find((c) => c.grade === null)
          return (
            <section key={items[0].specialization.id} className="flex flex-col gap-2">
              {!specializationId && (
                <h3 className="text-sm font-medium">{items[0].specialization.title}</h3>
              )}
              {/* На телефоне сетка в две колонки: плитки по ширине текста шли бы по одной. */}
              <ul className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
                {graded.map((c) => (
                  <li key={c.grade.id}>
                    <button
                      type="button"
                      onClick={() => onSelect(c)}
                      aria-pressed={selectedGradeId === c.grade.id}
                      className={cn(
                        'flex h-full w-full flex-col rounded-md border px-3 py-2 text-left text-sm hover:bg-muted',
                        selectedGradeId === c.grade.id && 'border-primary bg-accent',
                      )}
                    >
                      <span className="font-medium">{c.grade.title}</span>
                      <span className="text-xs text-muted-foreground">
                        {c.total} канд. · подтверждены {c.confirmed}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
              {untested && !recommendedLevels && (
                <p className="text-xs text-muted-foreground">
                  Ещё {untested.total} без теста: они в выдаче ниже, с пометкой «грейд не
                  подтверждён».
                </p>
              )}
            </section>
          )
        })}
      </CardContent>
    </Card>
  )
}
