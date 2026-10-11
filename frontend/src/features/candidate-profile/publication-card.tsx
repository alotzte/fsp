import { useQueryClient } from '@tanstack/react-query'

import {
  getGetMyCandidateProfileQueryKey,
  getGetMyEmployerViewQueryKey,
  useSaveMyProfilePrivacy,
} from '@/api/generated/candidate/candidate'
import type { CandidateProfileRead } from '@/api/generated/model'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { ConsentDocument } from '@/features/candidate-profile/consent-document'
import { useConsentMutations } from '@/features/candidate-profile/consents'
import { PROFILE_SECTION_LABELS, PROFILE_SECTIONS } from '@/features/candidate-profile/format'

export function PublicationCard({ profile }: { profile: CandidateProfileRead }) {
  const queryClient = useQueryClient()
  const { grant, revoke } = useConsentMutations()
  const privacy = useSaveMyProfilePrivacy({
    mutation: {
      onSuccess: (saved) => {
        queryClient.setQueryData(getGetMyCandidateProfileQueryKey(), saved)
        void queryClient.invalidateQueries({ queryKey: getGetMyEmployerViewQueryKey() })
      },
    },
  })
  const isPending = grant.isPending || revoke.isPending || privacy.isPending
  const error = grant.error ?? revoke.error ?? privacy.error
  const hidden = profile.hidden_sections

  return (
    <Card>
      <CardHeader>
        <CardTitle>Видимость</CardTitle>
        <CardDescription>
          {profile.is_published
            ? 'Профиль виден работодателям в поиске, но без ФИО и контактов.'
            : 'Профиль скрыт: работодатели его не найдут и не смогут пригласить.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <label className="flex items-center justify-between gap-4 text-sm font-medium">
          Показывать профиль работодателям
          <Switch
            checked={profile.is_published}
            disabled={!profile.exists || isPending}
            onCheckedChange={(checked) =>
              checked
                ? grant.mutate({ kind: 'profile_publication' })
                : revoke.mutate({ kind: 'profile_publication' })
            }
          />
        </label>
        {!profile.exists && (
          <p className="text-sm text-muted-foreground">Сначала сохраните профиль.</p>
        )}
        <fieldset className="flex flex-col gap-3" disabled={!profile.exists || isPending}>
          <legend className="mb-1 text-sm font-medium">До принятия приглашения показывать</legend>
          {PROFILE_SECTIONS.map((section) => (
            <label key={section} className="flex items-center justify-between gap-4 text-sm">
              {PROFILE_SECTION_LABELS[section]}
              <Switch
                checked={!hidden.includes(section)}
                disabled={!profile.exists || isPending}
                onCheckedChange={(shown) =>
                  privacy.mutate({
                    data: {
                      hidden_sections: shown
                        ? hidden.filter((item) => item !== section)
                        : [...hidden, section],
                    },
                  })
                }
              />
            </label>
          ))}
          <p className="text-xs text-muted-foreground">
            Скрытые разделы работодатель увидит вместе с контактами, когда вы примете приглашение.
            Город, формат работы и технологии скрыть нельзя: по ним считается совпадение с
            вакансией.
          </p>
        </fieldset>
        <details className="text-sm">
          <summary className="cursor-pointer text-primary">Текст согласия на показ</summary>
          <div className="mt-2">
            <ConsentDocument kind="profile_publication" />
          </div>
        </details>
        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error.message}</AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
  )
}
