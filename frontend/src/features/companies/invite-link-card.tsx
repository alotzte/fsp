import { useEffect, useState } from 'react'

import { useCreateCompanyInvite } from '@/api/generated/companies/companies'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'

const COPIED_HINT_MS = 2000
const dateTimeFormat = new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeStyle: 'short' })

type CopyState = 'idle' | 'copied' | 'failed'

export function InviteLinkCard() {
  const createInvite = useCreateCompanyInvite()
  const [copyState, setCopyState] = useState<CopyState>('idle')

  useEffect(() => {
    if (copyState !== 'copied') return
    const timer = window.setTimeout(() => setCopyState('idle'), COPIED_HINT_MS)
    return () => window.clearTimeout(timer)
  }, [copyState])

  const invite = createInvite.data

  async function copyLink(url: string) {
    try {
      await navigator.clipboard.writeText(url)
      setCopyState('copied')
    } catch {
      // Clipboard API недоступен вне защищённого контекста (http не на localhost).
      setCopyState('failed')
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Пригласить рекрутера</CardTitle>
        <CardDescription>
          Ссылка одноразовая: по ней в компанию вступит один коллега.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {invite && (
          <>
            <div className="flex gap-2">
              <Input readOnly value={invite.url} onFocus={(event) => event.target.select()} />
              <Button variant="outline" onClick={() => void copyLink(invite.url)}>
                {copyState === 'copied' ? 'Скопировано' : 'Копировать'}
              </Button>
            </div>
            <p className="text-sm text-muted-foreground">
              Действует до {dateTimeFormat.format(new Date(invite.expires_at))}
              {copyState === 'failed' && ' · скопируйте ссылку вручную'}
            </p>
          </>
        )}
        {createInvite.isError && (
          <Alert variant="destructive">
            <AlertDescription>{createInvite.error.message}</AlertDescription>
          </Alert>
        )}
        <Button
          className="self-start"
          variant={invite ? 'secondary' : 'default'}
          disabled={createInvite.isPending}
          onClick={() => createInvite.mutate()}
        >
          {invite ? 'Создать ещё одну ссылку' : 'Создать ссылку'}
        </Button>
      </CardContent>
    </Card>
  )
}
