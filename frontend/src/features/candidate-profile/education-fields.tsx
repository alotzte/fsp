import { PlusIcon, Trash2Icon } from 'lucide-react'
import { useFieldArray, useFormContext } from 'react-hook-form'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { FieldError } from '@/features/candidate-profile/field-error'
import type { ProfileFormValues } from '@/features/candidate-profile/form-schema'

export function EducationFields() {
  const { control, register, formState } = useFormContext<ProfileFormValues>()
  const { fields, append, remove } = useFieldArray({ control, name: 'education' })
  const errors = formState.errors.education

  return (
    <div className="flex flex-col gap-4">
      {fields.map((field, index) => {
        const prefix = `education-${field.id}`
        return (
          <fieldset key={field.id} className="flex flex-col gap-3 rounded-lg border p-4">
            <div className="grid gap-3 sm:grid-cols-[2fr_2fr_1fr]">
              <div className="flex flex-col gap-2">
                <Label htmlFor={`${prefix}-institution`}>Учебное заведение</Label>
                <Input
                  id={`${prefix}-institution`}
                  {...register(`education.${index}.institution`)}
                />
                <FieldError message={errors?.[index]?.institution?.message} />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor={`${prefix}-specialty`}>Специальность</Label>
                <Input id={`${prefix}-specialty`} {...register(`education.${index}.specialty`)} />
                <FieldError message={errors?.[index]?.specialty?.message} />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor={`${prefix}-year`}>Год окончания</Label>
                <Input
                  id={`${prefix}-year`}
                  inputMode="numeric"
                  {...register(`education.${index}.graduation_year`)}
                />
                <FieldError message={errors?.[index]?.graduation_year?.message} />
              </div>
            </div>
            <Button
              type="button"
              variant="ghost"
              className="self-start text-destructive"
              onClick={() => remove(index)}
            >
              <Trash2Icon /> Удалить
            </Button>
          </fieldset>
        )
      })}
      <Button
        type="button"
        variant="outline"
        className="self-start"
        onClick={() => append({ institution: '', specialty: '', graduation_year: '' })}
      >
        <PlusIcon /> Добавить образование
      </Button>
    </div>
  )
}
