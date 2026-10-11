import { DownloadIcon } from 'lucide-react'

import { basePath } from '@/api/http-client'
import { Button } from '@/components/ui/button'

/** Скачивание PDF идёт обычной навигацией браузера с cookie сессии, а не через fetch: файл сохраняет
 * сам браузер. Путь берётся из сгенерированного `get...Url`, чтобы не расходиться с API. */
export function DownloadPdfButton({
  apiPath,
  label = 'Скачать PDF',
}: {
  apiPath: string
  label?: string
}) {
  return (
    <Button asChild variant="outline" size="sm">
      <a href={`${basePath}${apiPath}`} download>
        <DownloadIcon />
        {label}
      </a>
    </Button>
  )
}
