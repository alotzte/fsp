import { useEffect } from 'react'

import { PageLoader } from '@/components/page-loader'
import { loginUrl } from '@/features/auth/auth-urls'

/** Неавторизованного пользователя отправляет на вход и возвращает на `nextPath`. */
export function RedirectToLogin({ nextPath }: { nextPath: string }) {
  useEffect(() => {
    window.location.replace(loginUrl(nextPath))
  }, [nextPath])
  return <PageLoader />
}
