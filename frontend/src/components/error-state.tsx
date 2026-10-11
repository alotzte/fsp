import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'

export function ErrorState({ message }: { message: string }) {
  return (
    <Alert variant="destructive">
      <AlertTitle>Не удалось загрузить данные</AlertTitle>
      <AlertDescription>{message}</AlertDescription>
    </Alert>
  )
}
