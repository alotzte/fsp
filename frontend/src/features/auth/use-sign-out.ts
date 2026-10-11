import { useQueryClient } from '@tanstack/react-query'

import { useLogout } from '@/api/generated/auth/auth'

/** Завершает сессию на бэке, затем уводит браузер на выход из Keycloak. */
export function useSignOut() {
  const queryClient = useQueryClient()
  const logout = useLogout({
    mutation: {
      onSuccess: ({ logout_url }) => {
        queryClient.clear()
        window.location.assign(logout_url)
      },
    },
  })
  return { signOut: () => logout.mutate(), isPending: logout.isPending }
}
