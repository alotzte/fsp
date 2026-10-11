import { Navigate, Outlet, useLocation } from 'react-router'

import type { UserRole } from '@/api/generated/model'
import { ErrorState } from '@/components/error-state'
import { PageLoader } from '@/components/page-loader'
import { cabinetPath, useCurrentUser } from '@/features/auth/current-user'
import { RedirectToLogin } from '@/features/auth/redirect-to-login'

/**
 * Защита кабинета: пускает только вошедших с нужной ролью (без role пускает с любой выбранной).
 * Это удобство интерфейса; права на данные проверяет бэк в каждой ручке.
 */
export function RequireRole({ role }: { role?: UserRole }) {
  const current = useCurrentUser()
  const location = useLocation()
  const here = `${location.pathname}${location.search}`

  switch (current.status) {
    case 'loading':
      return <PageLoader />
    case 'error':
      return <ErrorState message={current.error.message} />
    case 'anonymous':
      return <RedirectToLogin nextPath={here} />
    case 'authenticated': {
      const { user } = current
      if (user.role === null) {
        return <Navigate to={`/onboarding?next=${encodeURIComponent(here)}`} replace />
      }
      if (role && user.role !== role) return <Navigate to={cabinetPath(user.role)} replace />
      return <Outlet />
    }
  }
}
