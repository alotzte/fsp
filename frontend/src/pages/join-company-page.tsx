import { useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router'

import {
  getGetMyCompanyQueryKey,
  useAcceptCompanyInvite,
} from '@/api/generated/companies/companies'
import { getGetMeQueryKey } from '@/api/generated/me/me'
import { ErrorState } from '@/components/error-state'
import { PageLoader } from '@/components/page-loader'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { loginUrl, registerUrl } from '@/features/auth/auth-urls'
import { useCurrentUser } from '@/features/auth/current-user'

export function JoinCompanyPage() {
  const { token = '' } = useParams()
  const current = useCurrentUser()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const accept = useAcceptCompanyInvite({
    mutation: {
      onSuccess: (details) => {
        queryClient.setQueryData(getGetMyCompanyQueryKey(), details)
        // После вступления у пользователя появились роль и компания.
        void queryClient.invalidateQueries({ queryKey: getGetMeQueryKey() })
        navigate('/employer', { replace: true })
      },
    },
  })
  const herePath = `/join/${token}`

  if (current.status === 'loading') return <PageLoader />
  if (current.status === 'error') return <ErrorState message={current.error.message} />

  return (
    <Card className="max-w-xl">
      <CardHeader>
        <CardTitle>Приглашение в компанию</CardTitle>
        <CardDescription>
          Коллега приглашает вас подбирать кандидатов от имени компании.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {current.status === 'anonymous' && (
          <div className="flex flex-wrap gap-2">
            <Button asChild>
              <a href={registerUrl(herePath)}>Зарегистрироваться</a>
            </Button>
            <Button asChild variant="outline">
              <a href={loginUrl(herePath)}>У меня есть аккаунт</a>
            </Button>
          </div>
        )}

        {current.status === 'authenticated' && current.user.role === 'candidate' && (
          <Alert variant="destructive">
            <AlertDescription>
              Вы вошли как кандидат. Чтобы работать за компанию, зарегистрируйте отдельный аккаунт
              на другой email.
            </AlertDescription>
          </Alert>
        )}

        {current.status === 'authenticated' && current.user.company && (
          <Alert>
            <AlertDescription>
              Вы уже состоите в компании «{current.user.company.name}».{' '}
              <Link to="/employer" className="text-primary underline-offset-4 hover:underline">
                Перейти в кабинет
              </Link>
            </AlertDescription>
          </Alert>
        )}

        {current.status === 'authenticated' &&
          current.user.role !== 'candidate' &&
          !current.user.company && (
            <>
              {accept.isError && (
                <Alert variant="destructive">
                  <AlertDescription>{accept.error.message}</AlertDescription>
                </Alert>
              )}
              <Button
                className="self-start"
                disabled={accept.isPending}
                onClick={() => accept.mutate({ token })}
              >
                Вступить в компанию
              </Button>
            </>
          )}
      </CardContent>
    </Card>
  )
}
