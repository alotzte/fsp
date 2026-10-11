import { useQueryClient } from '@tanstack/react-query'
import { useId, useRef, useState } from 'react'

import {
  getGetMyCompanyQueryKey,
  useUploadMyCompanyLogo,
} from '@/api/generated/companies/companies'
import { Button } from '@/components/ui/button'
import { CompanyLogo } from '@/features/companies/company-logo'

// Совпадает с LOGO_MAX_BYTES на бэке: проверяем заранее, чтобы не гонять лишний файл.
const LOGO_MAX_BYTES = 2 * 1024 * 1024
const ACCEPTED_TYPES = 'image/png,image/jpeg,image/webp'

export function LogoUpload({
  logoUrl,
  companyName,
}: {
  logoUrl: string | null
  companyName: string
}) {
  const inputId = useId()
  const inputRef = useRef<HTMLInputElement>(null)
  const [localError, setLocalError] = useState<string | null>(null)
  const queryClient = useQueryClient()
  const upload = useUploadMyCompanyLogo({
    mutation: {
      onSuccess: (details) => queryClient.setQueryData(getGetMyCompanyQueryKey(), details),
    },
  })

  function handleFile(file: File | undefined) {
    if (!file) return
    if (file.size > LOGO_MAX_BYTES) {
      setLocalError('Файл больше 2 МБ')
      return
    }
    setLocalError(null)
    upload.mutate({ data: { file } })
  }

  const error = localError ?? (upload.isError ? upload.error.message : null)

  return (
    <div className="flex items-center gap-4">
      <CompanyLogo logoUrl={logoUrl} name={companyName} />
      <div className="flex flex-col gap-1">
        <input
          ref={inputRef}
          id={inputId}
          type="file"
          accept={ACCEPTED_TYPES}
          className="sr-only"
          onChange={(event) => {
            handleFile(event.target.files?.[0])
            // Сбрасываем, чтобы повторный выбор того же файла снова вызвал onChange.
            event.target.value = ''
          }}
        />
        <Button
          type="button"
          variant="outline"
          disabled={upload.isPending}
          onClick={() => inputRef.current?.click()}
        >
          {upload.isPending ? 'Загружаем...' : logoUrl ? 'Заменить логотип' : 'Загрузить логотип'}
        </Button>
        <span className="text-xs text-muted-foreground">PNG, JPEG или WebP, до 2 МБ</span>
        {error && <span className="text-sm text-destructive">{error}</span>}
      </div>
    </div>
  )
}
