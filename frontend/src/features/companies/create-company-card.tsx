import { zodResolver } from '@hookform/resolvers/zod'
import { useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import { useCreateCompany, getGetMyCompanyQueryKey } from '@/api/generated/companies/companies'
import { getGetMeQueryKey } from '@/api/generated/me/me'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'

// Ограничения повторяют CompanyCreate на бэке (backend/app/schemas/companies.py).
const COMPANY_NAME_MIN = 2
const COMPANY_NAME_MAX = 200
const COMPANY_DESCRIPTION_MAX = 2000

const companySchema = z.object({
  name: z
    .string()
    .trim()
    .min(COMPANY_NAME_MIN, `Минимум ${COMPANY_NAME_MIN} символа`)
    .max(COMPANY_NAME_MAX, `Максимум ${COMPANY_NAME_MAX} символов`),
  description: z
    .string()
    .trim()
    .max(COMPANY_DESCRIPTION_MAX, `Максимум ${COMPANY_DESCRIPTION_MAX} символов`),
})

type CompanyFormValues = z.infer<typeof companySchema>

export function CreateCompanyCard() {
  const queryClient = useQueryClient()
  const form = useForm<CompanyFormValues>({
    resolver: zodResolver(companySchema),
    defaultValues: { name: '', description: '' },
  })
  const createCompany = useCreateCompany({
    mutation: {
      onSuccess: (details) => {
        queryClient.setQueryData(getGetMyCompanyQueryKey(), details)
        // В /me появилась компания: перечитываем, чтобы кабинет переключился на неё.
        void queryClient.invalidateQueries({ queryKey: getGetMeQueryKey() })
      },
    },
  })
  const { errors } = form.formState

  return (
    <Card className="max-w-2xl">
      <CardHeader>
        <CardTitle>Создайте компанию</CardTitle>
        <CardDescription>
          От имени компании вы будете приглашать кандидатов. Коллег-рекрутеров добавите по ссылке.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form
          className="flex flex-col gap-4"
          onSubmit={form.handleSubmit((values) => createCompany.mutate({ data: values }))}
          noValidate
        >
          <div className="flex flex-col gap-2">
            <Label htmlFor="company-name">Название</Label>
            <Input id="company-name" aria-invalid={!!errors.name} {...form.register('name')} />
            {errors.name && <p className="text-sm text-destructive">{errors.name.message}</p>}
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="company-description">Чем занимается компания</Label>
            <Textarea
              id="company-description"
              rows={4}
              aria-invalid={!!errors.description}
              {...form.register('description')}
            />
            {errors.description && (
              <p className="text-sm text-destructive">{errors.description.message}</p>
            )}
          </div>
          {createCompany.isError && (
            <Alert variant="destructive">
              <AlertDescription>{createCompany.error.message}</AlertDescription>
            </Alert>
          )}
          <Button type="submit" className="self-start" disabled={createCompany.isPending}>
            Создать компанию
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}
