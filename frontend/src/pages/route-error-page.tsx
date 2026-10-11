import { isRouteErrorResponse, useRouteError } from 'react-router'

export function RouteErrorPage() {
  const error = useRouteError()
  const message = isRouteErrorResponse(error)
    ? `${error.status} ${error.statusText}`
    : error instanceof Error
      ? error.message
      : 'Неизвестная ошибка'

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-8">
      <h1 className="text-2xl font-semibold">Что-то пошло не так</h1>
      <p className="text-muted-foreground">{message}</p>
    </div>
  )
}
