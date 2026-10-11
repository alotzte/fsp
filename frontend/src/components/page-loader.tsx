import { Skeleton } from '@/components/ui/skeleton'

export function PageLoader() {
  return (
    <div className="flex flex-col gap-4" aria-busy="true" aria-label="Загрузка">
      <Skeleton className="h-8 w-64" />
      <Skeleton className="h-32 w-full" />
    </div>
  )
}
