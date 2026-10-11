import { useState } from 'react'

import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { ConsentDocument } from '@/features/candidate-profile/consent-document'
import { useConsentMutations } from '@/features/candidate-profile/consents'

/** Без согласия на обработку данных профиль не сохранить (152-ФЗ): спрашиваем его первым. */
export function ConsentGate() {
  const [accepted, setAccepted] = useState(false)
  const { grant } = useConsentMutations()

  return (
    <Card className="max-w-2xl">
      <CardHeader>
        <CardTitle>Согласие на обработку персональных данных</CardTitle>
        <CardDescription>
          Чтобы заполнить профиль, нужно ваше согласие. Показывать профиль работодателям вы решите
          отдельно, после заполнения.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <ConsentDocument kind="data_processing" />
        <label className="flex items-start gap-2 text-sm">
          <Checkbox
            checked={accepted}
            onCheckedChange={(checked) => setAccepted(checked === true)}
          />
          Я прочитал(а) текст и даю согласие на обработку моих персональных данных
        </label>
        {grant.isError && (
          <Alert variant="destructive">
            <AlertDescription>{grant.error.message}</AlertDescription>
          </Alert>
        )}
        <Button
          className="self-start"
          disabled={!accepted || grant.isPending}
          onClick={() => grant.mutate({ kind: 'data_processing' })}
        >
          Продолжить
        </Button>
      </CardContent>
    </Card>
  )
}
