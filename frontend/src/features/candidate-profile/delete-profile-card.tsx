import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useConsentMutations } from '@/features/candidate-profile/consents'

/** Отзыв согласия на обработку данных: по 152-ФЗ это удаление профиля. */
export function DeleteProfileCard() {
  const { revoke } = useConsentMutations()

  return (
    <Card>
      <CardHeader>
        <CardTitle>Отзыв согласия</CardTitle>
        <CardDescription>
          Если отозвать согласие на обработку данных, профиль будет удалён.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button variant="destructive" disabled={revoke.isPending}>
              Отозвать и удалить профиль
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Удалить профиль?</AlertDialogTitle>
              <AlertDialogDescription>
                Профиль, опыт, образование и навыки будут удалены без возможности восстановления.
                Аккаунт останется, и профиль можно будет заполнить заново.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Отмена</AlertDialogCancel>
              <AlertDialogAction
                className="bg-destructive text-white hover:bg-destructive/90"
                onClick={() => revoke.mutate({ kind: 'data_processing' })}
              >
                Удалить профиль
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </CardContent>
    </Card>
  )
}
