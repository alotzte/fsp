import { Link, Outlet } from 'react-router'

import logoFull from '@/assets/brand/logo-full.svg'
import { UserMenu } from '@/components/layout/user-menu'
import { useCurrentUser } from '@/features/auth/current-user'
import { NotificationsWatcher } from '@/features/notifications/notifications'

export function AppShell() {
  return (
    <div className="flex min-h-svh flex-col">
      <header className="border-b">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-6 px-4">
          <Link to="/" aria-label="На главную">
            <img
              src={logoFull}
              alt="Федерация спортивного программирования России"
              className="h-8"
            />
          </Link>
          <UserMenu />
        </div>
      </header>
      <DemoBanner />
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">
        <Outlet />
      </main>
      <NotificationsWatcher />
    </div>
  )
}

/** Напоминание, что это песочница жюри, а не настоящий аккаунт. */
function DemoBanner() {
  const current = useCurrentUser()
  if (current.status !== 'authenticated' || !current.user.is_demo) return null
  return (
    <div className="bg-accent text-accent-foreground">
      <p className="mx-auto max-w-6xl px-4 py-2 text-sm">
        Демо-песочница для проверки: данные удалятся через сутки. Другую роль откройте с главной
        страницы в окне инкогнито.
      </p>
    </div>
  )
}
