import { NavLink, useLocation } from 'react-router'

import { Button } from '@/components/ui/button'
import { loginUrl, registerUrl } from '@/features/auth/auth-urls'
import { cabinetPath, useCurrentUser } from '@/features/auth/current-user'
import { useSignOut } from '@/features/auth/use-sign-out'
import { CountBadge } from '@/features/notifications/notifications'
import { messagesCount, useNotifications } from '@/features/notifications/use-notifications'
import { cn } from '@/lib/utils'

const CABINET_LABELS = { candidate: 'Кабинет кандидата', employer: 'Кабинет работодателя' } as const

export function UserMenu() {
  const current = useCurrentUser()
  const { signOut, isPending } = useSignOut()
  const location = useLocation()
  const notifications = useNotifications()

  if (current.status === 'anonymous') {
    return (
      <div className="flex items-center gap-2">
        <Button asChild variant="ghost">
          <a href={loginUrl(returnPath(location.pathname, location.search))}>Войти</a>
        </Button>
        <Button asChild>
          <a href={registerUrl('/onboarding')}>Регистрация</a>
        </Button>
      </div>
    )
  }
  if (current.status !== 'authenticated') return null

  const { user } = current
  return (
    <div className="flex items-center gap-1 font-mono text-sm">
      {user.role && (
        <>
          <NavLink to={cabinetPath(user.role)} className={navClass}>
            <span className="hidden sm:inline">{CABINET_LABELS[user.role]}</span>
            <span className="sm:hidden">Кабинет</span>
            <CountBadge count={notifications?.invitations_to_answer ?? 0} />
          </NavLink>
          <NavLink to="/messages" className={navClass}>
            Сообщения
            <CountBadge count={messagesCount(notifications)} />
          </NavLink>
        </>
      )}
      <span className="hidden px-3 text-muted-foreground xl:inline">{user.email}</span>
      <Button variant="ghost" disabled={isPending} onClick={signOut}>
        Выйти
      </Button>
    </div>
  )
}

function navClass({ isActive }: { isActive: boolean }) {
  return cn(
    'flex items-center gap-1.5 rounded-md px-3 py-2 transition-colors hover:bg-accent hover:text-accent-foreground',
    isActive && 'bg-accent text-accent-foreground',
  )
}

/** Куда вернуться после входа. Без auth_error, иначе плашка «Не удалось войти» висела бы
 * и после успешного повторного входа. */
function returnPath(pathname: string, search: string): string {
  const params = new URLSearchParams(search)
  params.delete('auth_error')
  const query = params.toString()
  return query ? `${pathname}?${query}` : pathname
}
