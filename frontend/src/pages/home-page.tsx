import { Link, useSearchParams } from 'react-router'

import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { DemoCard } from '@/features/demo/demo-card'

export function HomePage() {
  const [searchParams] = useSearchParams()
  // Бэк возвращает сюда с ?auth_error=1, если вход через Keycloak не удался.
  const authFailed = searchParams.has('auth_error')

  return (
    <div className="flex flex-col gap-10">
      {authFailed && (
        <Alert variant="destructive">
          <AlertDescription>Не удалось войти. Попробуйте ещё раз.</AlertDescription>
        </Alert>
      )}
      <section className="flex max-w-3xl flex-col gap-4">
        <h1 className="text-4xl font-semibold tracking-tight text-primary">
          Работодатель сам находит вас
        </h1>
        <p className="text-lg text-muted-foreground">
          Пройдите тестирование, получите подтверждённую категорию и достижения ФСП в профиле, а
          приглашения с уровнем зарплаты придут сами.
        </p>
      </section>

      <DemoCard />

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Я ищу работу</CardTitle>
            <CardDescription>Профиль, тестирование на грейд, входящие приглашения.</CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild>
              <Link to="/candidate">В кабинет кандидата</Link>
            </Button>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Я ищу специалистов</CardTitle>
            <CardDescription>Подборка по категориям, поиск по базе, приглашения.</CardDescription>
          </CardHeader>
          <CardContent>
            <Button
              asChild
              variant="outline"
              className="border-primary text-primary hover:bg-accent hover:text-accent-foreground"
            >
              <Link to="/employer">В кабинет работодателя</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
