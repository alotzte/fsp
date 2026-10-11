import { useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router'

import { getGetMyFspQueryKey, useGetMyFsp, useUnlinkFspId } from '@/api/generated/fsp/fsp'
import type { CandidateProfileRead } from '@/api/generated/model'
import { basePath } from '@/api/http-client'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { ConsentDocument } from '@/features/candidate-profile/consent-document'
import { isConsentActive, useConsentMutations } from '@/features/candidate-profile/consents'
import { FspResults, FspSportRankLine } from '@/features/fsp/fsp-results'

const LINK_ERRORS: Record<string, string> = {
  taken: 'Этот ФСП ID уже привязан к другому профилю.',
  cancelled: 'Вход в ФСП ID отменён.',
  failed: 'Не удалось привязать ФСП ID, попробуйте ещё раз.',
  consent: 'Сначала дайте согласие на получение данных из реестра ФСП.',
}

// Привязка идёт переходом браузера: бэк уводит на вход в ФСП ID и возвращает сюда. Вкладка в адресе:
// без неё кабинет открыл бы приглашения, и итог привязки остался бы на скрытой вкладке.
const linkUrl = `${basePath}/api/v1/candidate/fsp/link?next=${encodeURIComponent('/candidate?tab=edit')}`

/** Привязка ФСП ID и результаты из реестра ФСП. */
export function FspCard({ profile }: { profile: CandidateProfileRead }) {
  const queryClient = useQueryClient()
  const { grant, revoke } = useConsentMutations()
  const consented = isConsentActive(profile.consents, 'fsp_data')
  const consentPending = grant.isPending || revoke.isPending
  const consentError = grant.error ?? revoke.error
  const [params] = useSearchParams()
  const fsp = useGetMyFsp()
  const unlink = useUnlinkFspId({
    mutation: {
      onSuccess: () => void queryClient.invalidateQueries({ queryKey: getGetMyFspQueryKey() }),
    },
  })
  const linkError = LINK_ERRORS[params.get('fsp_error') ?? '']

  return (
    <Card>
      <CardHeader>
        <CardTitle>ФСП ID</CardTitle>
        <CardDescription>
          Результаты соревнований Федерации спортивного программирования поднимают профиль в
          подборках внутри вашей категории. На грейд они не влияют.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <label className="flex items-center justify-between gap-4 text-sm font-medium">
          Согласие на получение данных из реестра ФСП
          <Switch
            checked={consented}
            disabled={consentPending}
            onCheckedChange={(checked) =>
              checked
                ? grant.mutate({ kind: 'fsp_data' })
                : revoke.mutate(
                    { kind: 'fsp_data' },
                    // Отзыв отвязывает ФСП ID: перечитываем карточку.
                    {
                      onSuccess: () =>
                        void queryClient.invalidateQueries({ queryKey: getGetMyFspQueryKey() }),
                    },
                  )
            }
          />
        </label>
        <details className="text-sm">
          <summary className="cursor-pointer text-primary">Текст согласия</summary>
          <div className="mt-2">
            <ConsentDocument kind="fsp_data" />
          </div>
        </details>
        {consentError && (
          <Alert variant="destructive">
            <AlertDescription>{consentError.message}</AlertDescription>
          </Alert>
        )}
        {linkError && (
          <Alert variant="destructive">
            <AlertDescription>{linkError}</AlertDescription>
          </Alert>
        )}
        {fsp.isPending && <Skeleton className="h-16 w-full" />}
        {fsp.isError && (
          <Alert variant="destructive">
            <AlertDescription>{fsp.error.message}</AlertDescription>
          </Alert>
        )}
        {fsp.isSuccess && !fsp.data.linked && (
          <>
            {consented ? (
              <Button asChild className="self-start">
                <a href={linkUrl}>Привязать ФСП ID</a>
              </Button>
            ) : (
              <Button className="self-start" disabled>
                Привязать ФСП ID
              </Button>
            )}
            <p className="text-xs text-muted-foreground">
              На стенде работает тестовый ФСП ID: войдите как athlete1-athlete4, пароль fsp-demo. У
              athlete4 истории соревнований нет.
            </p>
          </>
        )}
        {fsp.isSuccess && fsp.data.linked && (
          <>
            <p className="text-sm">
              Привязан <span className="font-mono">{fsp.data.fsp_id}</span>
            </p>
            {fsp.data.sport_rank && <FspSportRankLine rank={fsp.data.sport_rank} />}
            {fsp.data.results.length > 0 ? (
              <>
                <FspResults results={fsp.data.results} />
                <p className="text-xs text-muted-foreground">
                  В подборках учитываются победы, призовые места и финалы ({fsp.data.achievements}
                  ), участие без результата не считается.
                </p>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">
                В реестре ФСП пока нет ваших результатов. Это не понижает профиль: кандидаты без
                истории ФСП ранжируются по тесту и навыкам наравне с остальными.
              </p>
            )}
            <Button
              variant="ghost"
              size="sm"
              className="self-start"
              disabled={unlink.isPending}
              onClick={() => unlink.mutate()}
            >
              Отвязать
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  )
}
