import { BuildingIcon } from 'lucide-react'

import { basePath } from '@/api/http-client'
import { cn } from '@/lib/utils'

export function CompanyLogo({
  logoUrl,
  name,
  className,
}: {
  logoUrl: string | null
  name: string
  className?: string
}) {
  return (
    <div
      className={cn(
        'flex size-16 shrink-0 items-center justify-center overflow-hidden rounded-lg border bg-muted',
        className,
      )}
    >
      {logoUrl ? (
        <img
          src={`${basePath}${logoUrl}`}
          alt={`Логотип ${name}`}
          className="size-full object-contain"
        />
      ) : (
        <BuildingIcon className="size-1/2 text-muted-foreground" aria-hidden />
      )}
    </div>
  )
}
