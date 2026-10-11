import type { OptionStatus } from '@/api/generated/model'

/** Описания грейдов для самостоятельного выбора: кандидат заявляет грейд до теста. */
export const GRADE_HINTS: Record<string, string> = {
  intern: 'Учебные и пет-проекты, коммерческого опыта до полугода',
  junior: 'Решаю типовые задачи с подсказками старших, опыт до полутора лет',
  middle: 'Самостоятельно веду задачи от постановки до продакшена',
  senior: 'Проектирую решения и отвечаю за надёжность системы',
  lead: 'Определяю техническое направление и развиваю команду',
}

export const OPTION_STATUS_LABELS: Record<OptionStatus, string> = {
  available: 'доступен',
  offered: 'можно сразу',
  confirmed: 'подтверждён',
  cooldown: 'пока недоступен',
}

const dateFormat = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric',
  month: 'long',
  year: 'numeric',
})

export function formatDate(iso: string): string {
  return dateFormat.format(new Date(iso))
}

/** 125 → «2:05». */
export function formatCountdown(totalSeconds: number): string {
  const seconds = Math.max(0, Math.floor(totalSeconds))
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

/** Ниже этой устойчивости (вероятности, что повтор даст то же решение) результат считается «у границы
 * грейда»: там решение почти монетка при любом тесте. */
export const BORDERLINE_AGREEMENT = 0.65

/** 0.763 → «76%». */
export function formatPercent(share: number): string {
  return `${Math.round(100 * share)}%`
}

/** Страница попытки, маршрут в app/router.tsx. */
export function attemptPath(attemptId: string): string {
  return `/candidate/assessment/${attemptId}`
}
