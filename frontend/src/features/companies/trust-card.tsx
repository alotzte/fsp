import { ShieldCheckIcon } from 'lucide-react'
import { useState } from 'react'
import { useSearchParams } from 'react-router'

import { useRequestDomainCheck } from '@/api/generated/companies/companies'
import type { CompanyDetailsRead } from '@/api/generated/model'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

const DOMAIN_RESULTS: Record<string, { ok: boolean; text: string }> = {
  ok: { ok: true, text: 'Домен подтверждён.' },
  failed: { ok: false, text: 'Ссылка устарела или не подходит. Запросите письмо ещё раз.' },
}

/** Уровень доверия компании: от него зависит квота приглашений, кандидаты видят «домен
 * подтверждён». Заморозка наступает после жалоб нескольких кандидатов и снимается в админке. */
export function TrustCard({ company }: { company: CompanyDetailsRead }) {
  const [params] = useSearchParams()
  const [email, setEmail] = useState('')
  const request = useRequestDomainCheck()
  const result = DOMAIN_RESULTS[params.get('domain') ?? '']
  const isOwner = company.my_role === 'owner'

  return (
    <Card>
      <CardHeader>
        <CardTitle>Доверие</CardTitle>
        <CardDescription>
          Одновременно ждут ответа до {company.pending_quota} приглашений.{' '}
          {company.trust_level === 0 && 'Подтвердите домен сайта, чтобы квота выросла до 20.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        {company.frozen && (
          <Alert variant="destructive">
            <AlertDescription>
              Компания заморожена после жалоб кандидатов: приглашать и публиковать вакансии нельзя
              до разбора. Напишите в поддержку платформы.
            </AlertDescription>
          </Alert>
        )}
        {result && (
          <Alert variant={result.ok ? 'default' : 'destructive'}>
            <AlertDescription>{result.text}</AlertDescription>
          </Alert>
        )}
        {company.verified_domain ? (
          <p className="flex items-center gap-2">
            <ShieldCheckIcon className="size-4 text-primary" aria-hidden />
            Домен {company.verified_domain} подтверждён, кандидаты видят это в приглашениях.
          </p>
        ) : isOwner ? (
          <form
            className="flex flex-col gap-2"
            onSubmit={(event) => {
              event.preventDefault()
              request.mutate({ data: { email } })
            }}
          >
            <Label htmlFor="domain-email">Адрес в домене сайта компании</Label>
            <Input
              id="domain-email"
              type="email"
              placeholder={company.website ? 'hr@ваш-домен' : 'Сначала укажите сайт компании'}
              value={email}
              disabled={!company.website}
              onChange={(event) => setEmail(event.target.value)}
            />
            <Button
              type="submit"
              size="sm"
              className="self-start"
              disabled={!email || request.isPending}
            >
              Прислать ссылку
            </Button>
            {request.isSuccess && (
              <p className="text-muted-foreground">
                Письмо отправлено. Откройте ссылку из него в течение суток.
              </p>
            )}
            {request.isError && (
              <Alert variant="destructive">
                <AlertDescription>{request.error.message}</AlertDescription>
              </Alert>
            )}
          </form>
        ) : (
          <p className="text-muted-foreground">Домен может подтвердить владелец компании.</p>
        )}
      </CardContent>
    </Card>
  )
}
