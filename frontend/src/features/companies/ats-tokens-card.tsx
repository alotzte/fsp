import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import {
  getListAtsTokensQueryKey,
  useIssueAtsToken,
  useListAtsTokens,
  useRevokeAtsToken,
} from '@/api/generated/companies/companies'
import { basePath } from '@/api/http-client'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { formatDate } from '@/features/assessment/format'

/** Токены для ATS: внешняя система забирает ленту откликов, ответов и сообщений компании. */
export function AtsTokensCard() {
  const queryClient = useQueryClient()
  const [title, setTitle] = useState('')
  const tokens = useListAtsTokens()
  const refresh = () => void queryClient.invalidateQueries({ queryKey: getListAtsTokensQueryKey() })
  const issue = useIssueAtsToken({ mutation: { onSuccess: refresh } })
  const revoke = useRevokeAtsToken({ mutation: { onSuccess: refresh } })
  const error = issue.error ?? revoke.error

  return (
    <Card>
      <CardHeader>
        <CardTitle>API для ATS</CardTitle>
        <CardDescription>
          Хантфлоу, Talantix или своя система забирает новые отклики, ответы кандидатов и сообщения
          запросом <code className="font-mono text-xs">GET {basePath}/api/v1/ats/events</code> с
          токеном. Описание есть в{' '}
          <a href={`${basePath}/docs`} className="text-primary hover:underline">
            /docs
          </a>
          .
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        {issue.data && (
          <Alert>
            <AlertDescription className="flex flex-col gap-1">
              <span>
                Токен «{issue.data.title}». Скопируйте его сейчас, больше он не покажется:
              </span>
              <code className="font-mono text-xs break-all select-all">{issue.data.token}</code>
            </AlertDescription>
          </Alert>
        )}
        <form
          className="flex gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            issue.mutate({ data: { title } }, { onSuccess: () => setTitle('') })
          }}
        >
          <Input
            aria-label="Для какой системы"
            placeholder="Например, Хантфлоу"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />
          <Button type="submit" size="sm" disabled={!title.trim() || issue.isPending}>
            Выпустить
          </Button>
        </form>
        <ul className="flex flex-col divide-y">
          {tokens.data?.map((token) => (
            <li key={token.id} className="flex items-center justify-between gap-2 py-2">
              <span className="flex flex-col">
                <span>{token.title}</span>
                <span className="text-xs text-muted-foreground">
                  выпущен {formatDate(token.created_at)}
                  {token.last_used_at
                    ? ` · последний запрос ${formatDate(token.last_used_at)}`
                    : ' · ещё не использовался'}
                </span>
              </span>
              <Button
                variant="ghost"
                size="sm"
                disabled={revoke.isPending}
                onClick={() => revoke.mutate({ tokenId: token.id })}
              >
                Отозвать
              </Button>
            </li>
          ))}
        </ul>
        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error.message}</AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
  )
}
