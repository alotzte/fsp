import { PlusIcon, Trash2Icon } from 'lucide-react'
import { useFieldArray, useFormContext } from 'react-hook-form'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { FieldError } from '@/features/candidate-profile/field-error'
import type { ProfileFormValues } from '@/features/candidate-profile/form-schema'

/** Текущий месяц по местному времени (toISOString дал бы UTC). */
function currentMonth(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

export function ExperienceFields() {
  const { control, register, watch, setValue, formState } = useFormContext<ProfileFormValues>()
  const { fields, append, remove } = useFieldArray({ control, name: 'experience' })
  const errors = formState.errors.experience

  return (
    <div className="flex flex-col gap-4">
      {fields.map((field, index) => {
        const isCurrent = watch(`experience.${index}.ended_on`) === ''
        const prefix = `experience-${field.id}`
        return (
          <fieldset key={field.id} className="flex flex-col gap-3 rounded-lg border p-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="flex flex-col gap-2">
                <Label htmlFor={`${prefix}-company`}>Компания</Label>
                <Input id={`${prefix}-company`} {...register(`experience.${index}.company_name`)} />
                <FieldError message={errors?.[index]?.company_name?.message} />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor={`${prefix}-position`}>Должность</Label>
                <Input id={`${prefix}-position`} {...register(`experience.${index}.position`)} />
                <FieldError message={errors?.[index]?.position?.message} />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor={`${prefix}-start`}>Начало</Label>
                <Input
                  id={`${prefix}-start`}
                  type="month"
                  max={currentMonth()}
                  {...register(`experience.${index}.started_on`)}
                />
                <FieldError message={errors?.[index]?.started_on?.message} />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor={`${prefix}-end`}>Окончание</Label>
                <Input
                  id={`${prefix}-end`}
                  type="month"
                  max={currentMonth()}
                  disabled={isCurrent}
                  {...register(`experience.${index}.ended_on`)}
                />
                <label className="flex items-center gap-2 text-sm">
                  <Checkbox
                    checked={isCurrent}
                    onCheckedChange={(checked) =>
                      setValue(
                        `experience.${index}.ended_on`,
                        checked === true ? '' : currentMonth(),
                        {
                          shouldDirty: true,
                          shouldValidate: true,
                        },
                      )
                    }
                  />
                  Работаю сейчас
                </label>
                <FieldError message={errors?.[index]?.ended_on?.message} />
              </div>
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor={`${prefix}-description`}>Чем занимались</Label>
              <Textarea
                id={`${prefix}-description`}
                rows={3}
                {...register(`experience.${index}.description`)}
              />
              <FieldError message={errors?.[index]?.description?.message} />
            </div>
            <Button
              type="button"
              variant="ghost"
              className="self-start text-destructive"
              onClick={() => remove(index)}
            >
              <Trash2Icon /> Удалить место работы
            </Button>
          </fieldset>
        )
      })}
      <Button
        type="button"
        variant="outline"
        className="self-start"
        onClick={() =>
          append({ company_name: '', position: '', started_on: '', ended_on: '', description: '' })
        }
      >
        <PlusIcon /> Добавить место работы
      </Button>
    </div>
  )
}
