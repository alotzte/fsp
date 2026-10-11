import { useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router'

import {
  getListHiringNeedsQueryKey,
  useDeleteHiringNeed,
  useListHiringNeeds,
} from '@/api/generated/employer/employer'
import type { HiringNeedRead } from '@/api/generated/model'
import { ErrorState } from '@/components/error-state'
import { PageLoader } from '@/components/page-loader'
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
import { WORK_FORMAT_LABELS } from '@/features/candidate-profile/format'
import { candidatesPath } from '@/features/hiring/paths'
import { formatSalaryRange } from '@/features/invitations/format'

export function NeedsPage() {
  const needs = useListHiringNeeds()

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-sm text-muted-foreground">
          Опишите, кого ищете, и платформа соберёт подборку из кандидатов нужной категории и
          объяснит, почему каждый в ней. Приглашение с вилкой отправляете вы сами.
        </p>
        <Button asChild>
          <Link to="/employer/needs/new">Новая потребность</Link>
        </Button>
      </div>
      {needs.isPending && <PageLoader />}
      {needs.isError && <ErrorState message={needs.error.message} />}
      {needs.data?.length === 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Потребностей пока нет</CardTitle>
            <CardDescription>
              Создайте первую или ищите по всему банку кандидатов в разделе «Кандидаты».
            </CardDescription>
          </CardHeader>
        </Card>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        {needs.data?.map((need) => (
          <NeedCard key={need.id} need={need} />
        ))}
      </div>
    </div>
  )
}

function NeedCard({ need }: { need: HiringNeedRead }) {
  const queryClient = useQueryClient()
  const remove = useDeleteHiringNeed({
    mutation: {
      onSuccess: () =>
        void queryClient.invalidateQueries({ queryKey: getListHiringNeedsQueryKey() }),
    },
  })
  const place = [need.work_formats.map((f) => WORK_FORMAT_LABELS[f]).join(', '), need.city].filter(
    Boolean,
  )

  return (
    <Card>
      <CardHeader>
        <CardDescription>
          {need.specialization.title} · {need.grade.title}
        </CardDescription>
        <CardTitle className="text-lg">{need.title}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <p className="font-mono text-sm">
          {formatSalaryRange(need.salary_from_rub, need.salary_to_rub)}
          {place.length > 0 && ` · ${place.join(' · ')}`}
        </p>
        {need.skills.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {need.skills.map((s) => (
              <Badge key={s.skill_id} variant={s.must_have ? 'secondary' : 'outline'}>
                {s.title}
              </Badge>
            ))}
          </div>
        )}
        <div className="flex flex-wrap gap-2">
          <Button asChild>
            <Link to={candidatesPath({ need: need.id })}>Подборка кандидатов</Link>
          </Button>
          <Button asChild variant="outline">
            <Link to={`/employer/needs/${need.id}`}>Изменить</Link>
          </Button>
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="ghost" disabled={remove.isPending}>
                Удалить
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Удалить потребность?</AlertDialogTitle>
                <AlertDialogDescription>
                  Отправленные по ней приглашения останутся, но без привязки к потребности.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Отмена</AlertDialogCancel>
                <AlertDialogAction onClick={() => remove.mutate({ needId: need.id })}>
                  Удалить
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      </CardContent>
    </Card>
  )
}
