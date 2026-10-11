import { zodResolver } from '@hookform/resolvers/zod'
import { useQueryClient } from '@tanstack/react-query'
import { Controller, FormProvider, useForm } from 'react-hook-form'

import {
  getGetMyCandidateProfileQueryKey,
  getGetMyEmployerViewQueryKey,
  useSaveMyCandidateProfile,
} from '@/api/generated/candidate/candidate'
import { useListSpecializations } from '@/api/generated/dictionaries/dictionaries'
import type { CandidateProfileRead } from '@/api/generated/model'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
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
import { EducationFields } from '@/features/candidate-profile/education-fields'
import { ExperienceFields } from '@/features/candidate-profile/experience-fields'
import { FieldError } from '@/features/candidate-profile/field-error'
import {
  profileFormSchema,
  toFormValues,
  toPayload,
  type ProfileFormValues,
} from '@/features/candidate-profile/form-schema'
import { WORK_FORMAT_LABELS, WORK_FORMATS } from '@/features/candidate-profile/format'
import { ResumeImport } from '@/features/candidate-profile/resume-import'
import { SkillsInput } from '@/features/candidate-profile/skills-input'

// Radix Select не принимает пустую строку как значение: «не выбрано» кодируем отдельно.
const NO_SPECIALIZATION = 'none'

export function ProfileForm({ profile }: { profile: CandidateProfileRead }) {
  const queryClient = useQueryClient()
  const specializations = useListSpecializations()
  const form = useForm<ProfileFormValues>({
    resolver: zodResolver(profileFormSchema),
    defaultValues: toFormValues(profile),
  })
  const save = useSaveMyCandidateProfile({
    mutation: {
      onSuccess: (saved) => {
        queryClient.setQueryData(getGetMyCandidateProfileQueryKey(), saved)
        void queryClient.invalidateQueries({ queryKey: getGetMyEmployerViewQueryKey() })
        // Сбрасываем «грязное» состояние: бэк мог нормализовать значения (теги, Telegram).
        form.reset(toFormValues(saved))
      },
    },
  })
  const { errors, isDirty } = form.formState
  const { register, control } = form

  return (
    <FormProvider {...form}>
      <form
        className="flex flex-col gap-4"
        noValidate
        onSubmit={form.handleSubmit((values) => save.mutate({ data: toPayload(values) }))}
      >
        <ResumeImport />

        <Card>
          <CardHeader>
            <CardTitle>Основное</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-3">
            <div className="flex flex-col gap-2">
              <Label htmlFor="last-name">Фамилия</Label>
              <Input id="last-name" autoComplete="family-name" {...register('last_name')} />
              <FieldError message={errors.last_name?.message} />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="first-name">Имя</Label>
              <Input id="first-name" autoComplete="given-name" {...register('first_name')} />
              <FieldError message={errors.first_name?.message} />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="middle-name">Отчество</Label>
              <Input id="middle-name" autoComplete="additional-name" {...register('middle_name')} />
              <FieldError message={errors.middle_name?.message} />
            </div>
            <div className="flex flex-col gap-2 sm:col-span-2">
              <Label htmlFor="specialization">Желаемая специализация</Label>
              <Controller
                control={control}
                name="specialization_id"
                render={({ field }) => (
                  <Select
                    value={field.value === null ? NO_SPECIALIZATION : String(field.value)}
                    onValueChange={(value) =>
                      field.onChange(value === NO_SPECIALIZATION ? null : Number(value))
                    }
                  >
                    <SelectTrigger id="specialization" className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={NO_SPECIALIZATION}>Не выбрана</SelectItem>
                      {specializations.data?.map((specialization) => (
                        <SelectItem key={specialization.id} value={String(specialization.id)}>
                          {specialization.title}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="city">Город</Label>
              <Input id="city" autoComplete="address-level2" {...register('city')} />
              <FieldError message={errors.city?.message} />
            </div>
            <div className="flex flex-col gap-2 sm:col-span-2">
              <span className="text-sm font-medium">Формат работы</span>
              <Controller
                control={control}
                name="work_formats"
                render={({ field }) => (
                  <div className="flex flex-wrap gap-4">
                    {WORK_FORMATS.map((format) => (
                      <label key={format} className="flex items-center gap-2 text-sm">
                        <Checkbox
                          checked={field.value.includes(format)}
                          onCheckedChange={(checked) =>
                            field.onChange(
                              checked === true
                                ? [...field.value, format]
                                : field.value.filter((selected) => selected !== format),
                            )
                          }
                        />
                        {WORK_FORMAT_LABELS[format]}
                      </label>
                    ))}
                  </div>
                )}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="salary">Ожидания, от ₽ в месяц до вычета НДФЛ</Label>
              <Input id="salary" inputMode="numeric" {...register('salary_expectation_rub')} />
              <FieldError message={errors.salary_expectation_rub?.message} />
              <p className="text-xs text-muted-foreground">
                Работодатель эту сумму не видит: приглашение с вилкой ниже неё не будет отправлено.
              </p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Контакты</CardTitle>
            <CardDescription>
              Их увидит только работодатель, чьё приглашение вы примете.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-3">
            <div className="flex flex-col gap-2">
              <Label htmlFor="email">Email</Label>
              <Input id="email" value={profile.email} readOnly disabled />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="phone">Телефон</Label>
              <Input id="phone" type="tel" autoComplete="tel" {...register('phone')} />
              <FieldError message={errors.phone?.message} />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="telegram">Telegram</Label>
              <Input id="telegram" placeholder="@nickname" {...register('telegram')} />
              <FieldError message={errors.telegram?.message} />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Навыки</CardTitle>
            <CardDescription>
              Выбирайте из подсказок, так вас точнее найдут по фильтрам. Если нужного нет, нажмите
              Enter, и навык добавится как ваш собственный.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-6">
            <Controller
              control={control}
              name="technologies"
              render={({ field }) => (
                <SkillsInput
                  kind="technology"
                  label="Технологии"
                  placeholder="Python, React, PostgreSQL..."
                  value={field.value}
                  onChange={field.onChange}
                />
              )}
            />
            <Controller
              control={control}
              name="soft_skills"
              render={({ field }) => (
                <SkillsInput
                  kind="soft"
                  label="Софт-скиллы"
                  placeholder="Работа в команде, наставничество..."
                  value={field.value}
                  onChange={field.onChange}
                />
              )}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Опыт работы</CardTitle>
            <CardDescription>
              Названия компаний работодатели увидят только после того, как вы примете их
              приглашение. Контакты и ссылки в описании до этого тоже скрыты.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ExperienceFields />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Образование</CardTitle>
          </CardHeader>
          <CardContent>
            <EducationFields />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>О себе</CardTitle>
            <CardDescription>
              Этот текст видят работодатели до приглашения. Email, телефон, ссылки и @ник в нём
              скрываются, пока вы не примете приглашение.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Textarea id="about" rows={5} aria-label="О себе" {...register('about')} />
            <FieldError message={errors.about?.message} />
          </CardContent>
        </Card>

        {save.isError && (
          <Alert variant="destructive">
            <AlertDescription>{save.error.message}</AlertDescription>
          </Alert>
        )}
        {Object.keys(errors).length > 0 && (
          <Alert variant="destructive">
            <AlertDescription>Проверьте поля, отмеченные выше.</AlertDescription>
          </Alert>
        )}

        <div className="sticky bottom-0 -mx-4 flex items-center gap-3 border-t bg-background/95 px-4 py-3 backdrop-blur">
          <Button type="submit" disabled={save.isPending}>
            Сохранить профиль
          </Button>
          <span className="text-sm text-muted-foreground">
            {save.isPending
              ? 'Сохраняем...'
              : isDirty
                ? 'Есть несохранённые изменения'
                : save.isSuccess
                  ? 'Сохранено'
                  : null}
          </span>
        </div>
      </form>
    </FormProvider>
  )
}
