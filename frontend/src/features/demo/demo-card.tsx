import { useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router'

import { useDemoLogin, useGetDemoConfig } from '@/api/generated/demo/demo'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { cabinetPath, useCurrentUser } from '@/features/auth/current-user'

/** Вход для жюри в песочницу без регистрации. Показывается, только если на стенде DEMO_MODE. */
export function DemoCard() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const config = useGetDemoConfig()
  const login = useDemoLogin({
    mutation: {
      onSuccess: async ({ role }) => {
        // Сессия сменилась: всё закэшированное относилось к прежнему пользователю. Сброс, а не
        // удаление: шапка и баннер песочницы уже на экране и должны получить нового пользователя.
        await queryClient.resetQueries()
        void navigate(cabinetPath(role))
      },
    },
  })
  const current = useCurrentUser()
  if (!config.data?.enabled) return null
  // Поверх настоящего входа песочницу не открываем: SSO-сессия Keycloak пережила бы её, и на
  // общем компьютере «Войти» после выхода из демо пустило бы в чужой аккаунт без пароля.
  const signedInForReal = current.status === 'authenticated' && !current.user.is_demo

  return (
    <Card className="border-primary">
      <CardHeader>
        <CardTitle>Проверка для жюри</CardTitle>
        <CardDescription>
          Вход без регистрации в отдельную песочницу. У демо-кандидата уже заполнен профиль, а тест
          на грейд проходите сами, можно экспресс-версию на 6 минут. У демо-работодателя готова
          компания и потребность. Чтобы видеть обе стороны сразу, откройте вторую роль в окне
          инкогнито. Песочницы удаляются через сутки.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {signedInForReal ? (
          <p className="text-sm text-muted-foreground">
            Вы вошли в свой аккаунт. Чтобы открыть песочницу, сначала выйдите.
          </p>
        ) : (
          <div className="flex flex-wrap gap-2">
            <Button
              disabled={login.isPending}
              onClick={() => login.mutate({ data: { role: 'candidate' } })}
            >
              Войти как демо-кандидат
            </Button>
            <Button
              variant="outline"
              disabled={login.isPending}
              onClick={() => login.mutate({ data: { role: 'employer' } })}
            >
              Войти как демо-работодатель
            </Button>
          </div>
        )}
        {login.isError && (
          <Alert variant="destructive">
            <AlertDescription>{login.error.message}</AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
  )
}
