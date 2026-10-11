import { useListConsentDocuments } from '@/api/generated/consents/consents'
import type { ConsentKind } from '@/api/generated/model'

/** Текст согласия с бэка: там же его версия, которая фиксируется при согласии. */
export function ConsentDocument({ kind }: { kind: ConsentKind }) {
  const documents = useListConsentDocuments()
  const document = documents.data?.find((item) => item.kind === kind)

  if (documents.isPending)
    return <p className="text-sm text-muted-foreground">Загрузка текста...</p>
  if (!document)
    return <p className="text-sm text-destructive">Не удалось загрузить текст согласия</p>

  return (
    <div className="max-h-64 overflow-y-auto rounded-md border bg-muted/40 p-4 text-sm leading-relaxed [overflow-wrap:anywhere] whitespace-pre-line">
      {document.text}
      <p className="mt-3 text-xs text-muted-foreground">Редакция от {document.version}</p>
    </div>
  )
}
