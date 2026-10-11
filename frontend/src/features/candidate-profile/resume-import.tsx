import { FileUpIcon } from 'lucide-react'
import { useRef, useState } from 'react'
import { useFormContext } from 'react-hook-form'

import { useParseMyResume } from '@/api/generated/candidate/candidate'
import type { ResumeDraftRead } from '@/api/generated/model'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { formatExperience } from '@/features/candidate-profile/format'
import { mergeResumeDraft, type ProfileFormValues } from '@/features/candidate-profile/form-schema'

// Совпадает с RESUME_MAX_BYTES на бэке (backend/app/services/resume.py).
const RESUME_MAX_BYTES = 5 * 1024 * 1024

/** «Заполнить из PDF»: бэк распознаёт резюме, форма получает черновик, сохраняет кандидат сам. */
export function ResumeImport() {
  const form = useFormContext<ProfileFormValues>()
  const inputRef = useRef<HTMLInputElement>(null)
  const [localError, setLocalError] = useState<string | null>(null)
  const [result, setResult] = useState<{ draft: ResumeDraftRead; filled: string[] } | null>(null)
  const parse = useParseMyResume({
    mutation: {
      onSuccess: (draft) => {
        const { values, filled } = mergeResumeDraft(form.getValues(), draft)
        // keepDefaultValues: форма остаётся «грязной», пока кандидат не сохранит профиль.
        form.reset(values, { keepDefaultValues: true })
        setResult({ draft, filled })
      },
    },
  })

  function handleFile(file: File | undefined) {
    if (!file) return
    if (file.size > RESUME_MAX_BYTES) {
      setLocalError('Файл больше 5 МБ')
      return
    }
    setLocalError(null)
    setResult(null)
    parse.mutate({ data: { file } })
  }

  const error = localError ?? (parse.isError ? parse.error.message : null)

  return (
    <Card>
      <CardHeader>
        <CardTitle>Заполнить из резюме</CardTitle>
        <CardDescription>
          Загрузите PDF, и мы распознаем контакты, навыки, места работы и стаж. Заполнятся только
          пустые поля; проверьте их и сохраните профиль. Файл не сохраняется.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf"
          className="sr-only"
          aria-label="PDF-резюме"
          onChange={(event) => {
            handleFile(event.target.files?.[0])
            // Сбрасываем, чтобы повторный выбор того же файла снова вызвал onChange.
            event.target.value = ''
          }}
        />
        <div>
          <Button
            type="button"
            variant="outline"
            disabled={parse.isPending}
            onClick={() => inputRef.current?.click()}
          >
            <FileUpIcon />
            {parse.isPending ? 'Распознаём...' : 'Загрузить PDF'}
          </Button>
        </div>
        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        {result && (
          <Alert>
            <AlertDescription className="flex flex-col gap-1">
              <span>
                {result.filled.length > 0
                  ? `Заполнено: ${result.filled.join(', ')}.`
                  : 'Новых данных не нашли: поля уже заполнены или резюме не распознано.'}
              </span>
              {result.draft.total_experience_months > 0 && (
                <span>
                  Стаж по резюме: {formatExperience(result.draft.total_experience_months)}.
                </span>
              )}
              {result.draft.grade && (
                <span>
                  В резюме указан грейд {result.draft.grade.title}. Подтвердить его можно тестом на
                  вкладке «Категория и тест».
                </span>
              )}
              {result.draft.experience.some((entry) => !entry.company_name || !entry.position) && (
                <span>У части мест работы не распознаны компания или должность, допишите их.</span>
              )}
            </AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
  )
}
