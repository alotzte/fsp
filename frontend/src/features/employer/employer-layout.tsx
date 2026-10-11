import { NavLink, Outlet } from 'react-router'

import { ErrorState } from '@/components/error-state'
import { PageLoader } from '@/components/page-loader'
import { useCurrentUser } from '@/features/auth/current-user'
import { CreateCompanyCard } from '@/features/companies/create-company-card'
import { CountBadge } from '@/features/notifications/notifications'
import { useNotifications } from '@/features/notifications/use-notifications'
import { cn } from '@/lib/utils'

const SECTIONS = [
  { to: '/employer', label: 'Потребности', end: true },
  { to: '/employer/candidates', label: 'Кандидаты', end: false },
  { to: '/employer/invitations', label: 'Приглашения', end: false },
  { to: '/employer/company', label: 'Компания', end: false },
]

/** Кабинет работодателя: без компании искать кандидатов и приглашать нельзя. */
export function EmployerLayout() {
  const current = useCurrentUser()
  const notifications = useNotifications()

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold">Кабинет работодателя</h1>
      {current.status === 'loading' && <PageLoader />}
      {current.status === 'error' && <ErrorState message={current.error.message} />}
      {current.status === 'authenticated' &&
        (current.user.company ? (
          <>
            <nav aria-label="Разделы кабинета" className="flex flex-wrap gap-1 border-b">
              {SECTIONS.map((section) => (
                <NavLink
                  key={section.to}
                  to={section.to}
                  end={section.end}
                  className={({ isActive }) =>
                    cn(
                      '-mb-px flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium transition-colors',
                      isActive
                        ? 'border-primary text-foreground'
                        : 'border-transparent text-muted-foreground hover:text-foreground',
                    )
                  }
                >
                  {section.label}
                  {section.to === '/employer/invitations' && (
                    <CountBadge count={notifications?.invitations_to_answer ?? 0} />
                  )}
                </NavLink>
              ))}
            </nav>
            <Outlet />
          </>
        ) : (
          <CreateCompanyCard />
        ))}
    </div>
  )
}
