import { zodResolver } from '@hookform/resolvers/zod'
import { Controller, useForm } from 'react-hook-form'
import { z } from 'zod'

import { useListGrades, useListSpecializations } from '@/api/generated/dictionaries/dictionaries'
import type { HiringNeedInput, HiringNeedRead, WorkFormat } from '@/api/generated/model'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardFooter } from '@/components/ui/card'
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
import { FieldError } from '@/features/candidate-profile/field-error'
import { WORK_FORMAT_LABELS, WORK_FORMATS } from '@/features/candidate-profile/format'
import { SkillsInput } from '@/features/candidate-profile/skills-input'
import { parseRub } from '@/features/invitations/format'

// Ограничения повторяют HiringNeedInput на бэке (backend/app/schemas/hiring.py).
// «150 000» это обычная запись суммы, пробелы убираем до проверки.
const salary = z
  .string()
  .transform((v) => v.replace(/\s/g, ''))
  .refine((v) => parseRub(v) !== null, 'Сумма в рублях, без копеек, до 10 000 000')
const skill = z.object({ skill_id: z.number().nullable(), title: z.string() })

const needSchema = z
  .object({
    title: z.string().trim().min(1, 'Обязательное поле').max(200, 'Максимум 200 символов'),
    description: z.string().trim().max(3000, 'Максимум 3000 символов'),
    specialization_id: z.number({ message: 'Выберите направление' }).nullable(),
    grade_id: z.number({ message: 'Выберите грейд' }).nullable(),
    must_skills: z.array(skill),
    nice_skills: z.array(skill),
    work_formats: z.array(z.enum(WORK_FORMATS as [WorkFormat, ...WorkFormat[]])),
    city: z.string().trim().max(100, 'Максимум 100 символов'),
    salary_from_rub: salary,
    salary_to_rub: salary,
    published: z.boolean(),
  })
  .refine((v) => v.specialization_id !== null, {
    message: 'Выберите направление',
    path: ['specialization_id'],
  })
  .refine((v) => v.grade_id !== null, { message: 'Выберите грейд', path: ['grade_id'] })
  .refine((v) => +v.salary_to_rub >= +v.salary_from_rub, {
    message: 'Верх вилки меньше нижней границы',
    path: ['salary_to_rub'],
  })

type NeedFormValues = z.infer<typeof needSchema>

function toFormValues(need: HiringNeedRead | undefined): NeedFormValues {
  const pick = (mustHave: boolean) =>
    (need?.skills ?? [])
      .filter((s) => s.must_have === mustHave)
      .map((s) => ({ skill_id: s.skill_id, title: s.title }))
  return {
    title: need?.title ?? '',
    description: need?.description ?? '',
    specialization_id: need?.specialization.id ?? null,
    grade_id: need?.grade.id ?? null,
    must_skills: pick(true),
    nice_skills: pick(false),
    work_formats: need?.work_formats ?? [],
    city: need?.city ?? '',
    salary_from_rub: need ? String(need.salary_from_rub) : '',
    salary_to_rub: need ? String(need.salary_to_rub) : '',
    published: need?.published_at != null,
  }
}

function toPayload(values: NeedFormValues): HiringNeedInput {
  const ids = (list: NeedFormValues['must_skills'], mustHave: boolean) =>
    list.flatMap((s) =>
      s.skill_id === null ? [] : [{ skill_id: s.skill_id, must_have: mustHave }],
    )
  const must = ids(values.must_skills, true)
  return {
    title: values.title,
    description: values.description,
    specialization_id: values.specialization_id ?? 0,
    grade_id: values.grade_id ?? 0,
    // Навык, отмеченный и обязательным, и желательным, считаем обязательным.
    skills: [
      ...must,
      ...ids(values.nice_skills, false).filter((n) => !must.some((m) => m.skill_id === n.skill_id)),
    ],
    work_formats: values.work_formats,
    city: values.city,
    salary_from_rub: Number(values.salary_from_rub),
    salary_to_rub: Number(values.salary_to_rub),
    published: values.published,
  }
}

export function NeedForm({
  need,
  isPending,
  error,
  submitLabel,
  onSubmit,
}: {
  need?: HiringNeedRead
  isPending: boolean
  error: Error | null
  submitLabel: string
  onSubmit: (payload: HiringNeedInput) => void
}) {
  const specializations = useListSpecializations()
  const grades = useListGrades()
  const form = useForm<NeedFormValues>({
    resolver: zodResolver(needSchema),
    defaultValues: toFormValues(need),
  })
  const { register, control } = form
  const { errors } = form.formState

  return (
    <form noValidate onSubmit={form.handleSubmit((values) => onSubmit(toPayload(values)))}>
      <Card>
        <CardContent className="grid gap-5 pt-6 sm:grid-cols-2">
          <div className="flex flex-col gap-2 sm:col-span-2">
            <Label htmlFor="need-title">Кого ищем</Label>
            <Input
              id="need-title"
              placeholder="Python-разработчик в команду платежей"
              {...register('title')}
            />
            <FieldError message={errors.title?.message} />
          </div>
          <div className="flex flex-col gap-2 sm:col-span-2">
            <Label htmlFor="need-description">Чем занимается команда и какие задачи</Label>
            <Textarea id="need-description" rows={4} {...register('description')} />
            <FieldError message={errors.description?.message} />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="need-specialization">Направление</Label>
            <Controller
              control={control}
              name="specialization_id"
              render={({ field }) => (
                <Select
                  value={field.value === null ? undefined : String(field.value)}
                  onValueChange={(value) => field.onChange(Number(value))}
                >
                  <SelectTrigger id="need-specialization" className="w-full">
                    <SelectValue placeholder="Выберите направление" />
                  </SelectTrigger>
                  <SelectContent>
                    {specializations.data?.map((s) => (
                      <SelectItem key={s.id} value={String(s.id)}>
                        {s.title}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            />
            <FieldError message={errors.specialization_id?.message} />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="need-grade">Грейд</Label>
            <Controller
              control={control}
              name="grade_id"
              render={({ field }) => (
                <Select
                  value={field.value === null ? undefined : String(field.value)}
                  onValueChange={(value) => field.onChange(Number(value))}
                >
                  <SelectTrigger id="need-grade" className="w-full">
                    <SelectValue placeholder="Выберите грейд" />
                  </SelectTrigger>
                  <SelectContent>
                    {grades.data?.map((g) => (
                      <SelectItem key={g.id} value={String(g.id)}>
                        {g.title}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            />
            <FieldError message={errors.grade_id?.message} />
          </div>
          <Controller
            control={control}
            name="must_skills"
            render={({ field }) => (
              <SkillsInput
                kind="technology"
                label="Обязательные навыки"
                placeholder="Python, PostgreSQL..."
                dictionaryOnly
                value={field.value}
                onChange={field.onChange}
              />
            )}
          />
          <Controller
            control={control}
            name="nice_skills"
            render={({ field }) => (
              <SkillsInput
                kind="technology"
                label="Желательные навыки"
                placeholder="Kafka, Kubernetes..."
                dictionaryOnly
                value={field.value}
                onChange={field.onChange}
              />
            )}
          />
          <fieldset className="flex flex-col gap-2">
            <legend className="mb-2 text-sm font-medium">Формат работы</legend>
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
                            checked
                              ? [...field.value, format]
                              : field.value.filter((f) => f !== format),
                          )
                        }
                      />
                      {WORK_FORMAT_LABELS[format]}
                    </label>
                  ))}
                </div>
              )}
            />
          </fieldset>
          <div className="flex flex-col gap-2">
            <Label htmlFor="need-city">Город офиса</Label>
            <Input id="need-city" placeholder="Москва" {...register('city')} />
            <FieldError message={errors.city?.message} />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="need-salary-from">Вилка от, ₽ в месяц до вычета НДФЛ</Label>
            <Input id="need-salary-from" inputMode="numeric" {...register('salary_from_rub')} />
            <FieldError message={errors.salary_from_rub?.message} />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="need-salary-to">до, ₽ в месяц до вычета НДФЛ</Label>
            <Input id="need-salary-to" inputMode="numeric" {...register('salary_to_rub')} />
            <FieldError message={errors.salary_to_rub?.message} />
          </div>
          <p className="text-sm text-muted-foreground sm:col-span-2">
            Вилку кандидат увидит в приглашении сразу. Если её верх ниже скрытых ожиданий кандидата,
            приглашение ему не отправится, а подборка покажет таких кандидатов отдельно.
          </p>
          <Controller
            control={control}
            name="published"
            render={({ field }) => (
              <label className="flex items-start gap-3 text-sm sm:col-span-2">
                <Checkbox
                  className="mt-0.5"
                  checked={field.value}
                  onCheckedChange={(checked) => field.onChange(checked === true)}
                />
                <span className="flex flex-col gap-1">
                  <span className="font-medium">Опубликовать как вакансию</span>
                  <span className="text-muted-foreground">
                    Кандидаты этого направления увидят вакансию и смогут откликнуться. Профиль и
                    контакты откликнувшегося открываются сразу; ответьте в течение 7 дней.
                  </span>
                </span>
              </label>
            )}
          />
        </CardContent>
        <CardFooter className="flex flex-col items-start gap-3">
          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error.message}</AlertDescription>
            </Alert>
          )}
          <Button type="submit" disabled={isPending}>
            {submitLabel}
          </Button>
        </CardFooter>
      </Card>
    </form>
  )
}
