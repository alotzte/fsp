import { useQueryClient } from '@tanstack/react-query'
import { Navigate, useNavigate, useSearchParams } from 'react-router'

import { getGetMeQueryKey, useChooseMyRole } from '@/api/generated/me/me'
import type { UserRole } from '@/api/generated/model'
import { ErrorState } from '@/components/error-state'
import { PageLoader } from '@/components/page-loader'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { cabinetPath, safeNextPath, useCurrentUser } from '@/features/auth/current-user'
import { RedirectToLogin } from '@/features/auth/redirect-to-login'

const ROLE_OPTIONS: { role: UserRole; title: string; description: string; action: string }[] = [
  {
    role: 'candidate',
    title: 'Я ищу работу',
    description: 'Пройду тестирование, получу категорию, а работодатели сами пришлют приглашения.',
    action: 'Я кандидат',
  },
  {
    role: 'employer',
    title: 'Я ищу специалистов',
    description: 'Создам компанию, буду подбирать кандидатов по категориям и приглашать их.',
    action: 'Я работодатель',
  },
]

export function OnboardingPage() {
  const current = useCurrentUser()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const chooseRole = useChooseMyRole({
    mutation: {
      onSuccess: (me) => {
        queryClient.setQueryData(getGetMeQueryKey(), me)
        if (me.role !== null) {
          navigate(safeNextPath(searchParams.get('next')) ?? cabinetPath(me.role), {
            replace: true,
          })
        }
      },
    },
  })

  if (current.status === 'loading') return <PageLoader />
  if (current.status === 'error') return <ErrorState message={current.error.message} />
  if (current.status === 'anonymous') return <RedirectToLogin nextPath="/onboarding" />
  if (current.user.role !== null) return <Navigate to={cabinetPath(current.user.role)} replace />

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold">Кто вы на платформе?</h1>
        <p className="text-muted-foreground">
          Роль выбирается один раз. Если коллега прислал ссылку-приглашение в компанию, откройте её,
          и роль выберется сама.
        </p>
      </div>

      {chooseRole.isError && (
        <Alert variant="destructive">
          <AlertDescription>{chooseRole.error.message}</AlertDescription>
        </Alert>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {ROLE_OPTIONS.map((option) => (
          <Card key={option.role}>
            <CardHeader>
              <CardTitle>{option.title}</CardTitle>
              <CardDescription>{option.description}</CardDescription>
            </CardHeader>
            <CardContent>
              <Button
                disabled={chooseRole.isPending}
                onClick={() => chooseRole.mutate({ data: { role: option.role } })}
              >
                {option.action}
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}
