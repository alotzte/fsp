import { zodResolver } from '@hookform/resolvers/zod'
import { useQueryClient } from '@tanstack/react-query'
import { Controller, useForm } from 'react-hook-form'
import { z } from 'zod'

import { getGetMyCompanyQueryKey, useUpdateMyCompany } from '@/api/generated/companies/companies'
import { useListIndustries } from '@/api/generated/dictionaries/dictionaries'
import { getGetMeQueryKey } from '@/api/generated/me/me'
import type { CompanyDetailsRead } from '@/api/generated/model'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { FieldError } from '@/features/candidate-profile/field-error'

// Ограничения повторяют CompanyUpdateInput на бэке (backend/app/schemas/companies.py).
const PHONE = /^\+?[0-9 ()-]{7,20}$/
const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/
const URL = /^https?:\/\/\S+$/i
const NO_INDUSTRY = 'none'

const optionalMatching = (pattern: RegExp, message: string, max: number) =>
  z
    .string()
    .trim()
    .max(max, `Максимум ${max} символов`)
    .refine((value) => value === '' || pattern.test(value), message)

const companySchema = z.object({
  name: z.string().trim().min(2, 'Минимум 2 символа').max(200, 'Максимум 200 символов'),
  description: z.string().trim().max(2000, 'Максимум 2000 символов'),
  industry_id: z.number().nullable(),
  website: optionalMatching(URL, 'Ссылка должна начинаться с http:// или https://', 300),
  contact_email: optionalMatching(EMAIL, 'Некорректный email', 320),
  contact_phone: optionalMatching(PHONE, 'Цифры, пробелы, скобки и дефисы', 20),
})

type CompanyFormValues = z.infer<typeof companySchema>

export function CompanyEditForm({
  company,
  onDone,
}: {
  company: CompanyDetailsRead
  onDone: () => void
}) {
  const queryClient = useQueryClient()
  const industries = useListIndustries()
  const form = useForm<CompanyFormValues>({
    resolver: zodResolver(companySchema),
    defaultValues: {
      name: company.name,
      description: company.description,
      industry_id: company.industry?.id ?? null,
      website: company.website,
      contact_email: company.contact_email,
      contact_phone: company.contact_phone,
    },
  })
  const update = useUpdateMyCompany({
    mutation: {
      onSuccess: (details) => {
        queryClient.setQueryData(getGetMyCompanyQueryKey(), details)
        // Название компании показывается и в /me (шапка, приглашения).
        void queryClient.invalidateQueries({ queryKey: getGetMeQueryKey() })
        onDone()
      },
    },
  })
  const { errors } = form.formState

  return (
    <form
      className="flex flex-col gap-4"
      noValidate
      onSubmit={form.handleSubmit((values) => update.mutate({ data: values }))}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-2">
          <Label htmlFor="company-name">Название</Label>
          <Input id="company-name" {...form.register('name')} />
          <FieldError message={errors.name?.message} />
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor="company-industry">Отрасль</Label>
          <Controller
            control={form.control}
            name="industry_id"
            render={({ field }) => (
              <Select
                value={field.value === null ? NO_INDUSTRY : String(field.value)}
                onValueChange={(value) =>
                  field.onChange(value === NO_INDUSTRY ? null : Number(value))
                }
              >
                <SelectTrigger id="company-industry" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NO_INDUSTRY}>Не указана</SelectItem>
                  {industries.data?.map((industry) => (
                    <SelectItem key={industry.id} value={String(industry.id)}>
                      {industry.title}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
        </div>
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="company-description">Чем занимается компания</Label>
        <Textarea id="company-description" rows={4} {...form.register('description')} />
        <FieldError message={errors.description?.message} />
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="flex flex-col gap-2">
          <Label htmlFor="company-website">Сайт</Label>
          <Input id="company-website" placeholder="https://" {...form.register('website')} />
          <FieldError message={errors.website?.message} />
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor="company-email">Email отдела найма</Label>
          <Input id="company-email" type="email" {...form.register('contact_email')} />
          <FieldError message={errors.contact_email?.message} />
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor="company-phone">Телефон</Label>
          <Input id="company-phone" type="tel" {...form.register('contact_phone')} />
          <FieldError message={errors.contact_phone?.message} />
        </div>
      </div>
      {update.isError && (
        <Alert variant="destructive">
          <AlertDescription>{update.error.message}</AlertDescription>
        </Alert>
      )}
      <div className="flex gap-2">
        <Button type="submit" disabled={update.isPending}>
          Сохранить
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Отмена
        </Button>
      </div>
    </form>
  )
}
