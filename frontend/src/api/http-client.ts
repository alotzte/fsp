/** Ошибка API в формате бэка: `{"error": "<ИмяИсключения>", "detail": "..."}` (backend/app/errors.py). */
export class ApiError extends Error {
  readonly status: number
  readonly code: string | null

  constructor(status: number, code: string | null, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

async function parseErrorBody(response: Response): Promise<ApiError> {
  const fallback = new ApiError(response.status, null, response.statusText)
  const contentType = response.headers.get('content-type') ?? ''
  if (!contentType.includes('application/json')) return fallback

  const body: unknown = await response.json()
  if (typeof body !== 'object' || body === null) return fallback
  const { error, detail } = body as { error?: unknown; detail?: unknown }
  return new ApiError(
    response.status,
    typeof error === 'string' ? error : null,
    typeof detail === 'string' ? detail : (validationMessage(detail) ?? response.statusText),
  )
}

/** Префикс публикации без завершающего слэша: '' или '/fsp'. Пути API и бэка: от него. */
export const basePath = import.meta.env.BASE_URL.replace(/\/$/, '')

/** FastAPI отдаёт ошибки валидации (422) списком `{loc, msg}` в detail: склеиваем тексты. */
function validationMessage(detail: unknown): string | null {
  if (!Array.isArray(detail)) return null
  const messages = detail
    .map((item: unknown) =>
      typeof item === 'object' && item !== null && 'msg' in item ? String(item.msg) : null,
    )
    .filter((message): message is string => message !== null)
    // Pydantic добавляет к нашим сообщениям префикс «Value error, ».
    .map((message) => message.replace(/^Value error, /, ''))
  return messages.length > 0 ? [...new Set(messages)].join('. ') : null
}

/**
 * Мутатор для orval. Бросает ApiError на не-2xx, чтобы TanStack Query переводил запрос в состояние error.
 * Запросы идут на тот же origin: в dev через прокси Vite, в Docker через nginx.
 */
export async function httpClient<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${basePath}${url}`, {
      ...init,
      headers: { Accept: 'application/json', ...init?.headers },
    })
  } catch {
    // fetch падает без ответа (нет сети, gateway лежит): приводим к ApiError, как обещает ErrorType.
    throw new ApiError(0, 'NetworkError', 'Нет связи с сервером')
  }
  if (!response.ok) throw await parseErrorBody(response)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

/** orval подставляет этот тип как TError во все сгенерированные хуки. Тело ошибки бэка одинаковое, поэтому параметр не используется. */
export type ErrorType<_ErrorBody> = ApiError
