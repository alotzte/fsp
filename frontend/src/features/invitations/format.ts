import type { DeclineReason, InvitationStatus, ReportReason } from '@/api/generated/model'
import { formatRub } from '@/features/candidate-profile/format'

export const INVITATION_STATUS_LABELS: Record<InvitationStatus, string> = {
  sent: 'отправлено',
  viewed: 'просмотрено',
  accepted: 'принято',
  declined: 'отклонено',
  withdrawn: 'отозвано',
  expired: 'истекло',
}

export const DECLINE_REASON_LABELS: Record<DeclineReason, string> = {
  salary: 'Не устраивает зарплата',
  stack: 'Не мой стек',
  format: 'Не подходит формат работы',
  not_looking: 'Сейчас не ищу работу',
  other: 'Другое',
}

export const DECLINE_REASONS = Object.keys(DECLINE_REASON_LABELS) as DeclineReason[]

/** Причины, с которыми компания отказывает на отклик (тот же DeclineReason на бэке). */
export const EMPLOYER_DECLINE_REASON_LABELS: Partial<Record<DeclineReason, string>> = {
  stack: 'Не тот стек',
  salary: 'Не сходимся по зарплате',
  format: 'Не подходит формат работы',
  other: 'Другое',
}

export const EMPLOYER_DECLINE_REASONS = Object.keys(
  EMPLOYER_DECLINE_REASON_LABELS,
) as DeclineReason[]

/** Причина отказа так, как её сформулировала сторона, которая отказала. */
export function declineReasonLabel(reason: DeclineReason, byEmployer: boolean): string {
  return (
    (byEmployer ? EMPLOYER_DECLINE_REASON_LABELS[reason] : undefined) ??
    DECLINE_REASON_LABELS[reason]
  )
}

/** Ждёт ответа кандидата. */
export function isPending(status: InvitationStatus): boolean {
  return status === 'sent' || status === 'viewed'
}

export function formatSalaryRange(from: number, to: number): string {
  const range = from === to ? formatRub(from) : `${formatRub(from)} - ${formatRub(to)}`
  // Организаторы: гросс или нетто, неважно, главное явно подписать.
  return `${range} до НДФЛ`
}

const dateTimeFormat = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
})

export function formatDateTime(iso: string): string {
  return dateTimeFormat.format(new Date(iso))
}

export const REPORT_REASON_LABELS: Record<ReportReason, string> = {
  fake_vacancy: 'Похоже на фиктивную вакансию',
  asked_money: 'Просили заплатить',
  terms_differ: 'Условия не совпадают с приглашением',
}

export const REPORT_REASONS = Object.keys(REPORT_REASON_LABELS) as ReportReason[]

// Ограничения повторяют SalaryRangeInput на бэке (backend/app/schemas/invitations.py).
export const MAX_SALARY_RUB = 10_000_000

/** «200 000» → 200000. Копейки, «1e6», ноль и больше MAX_SALARY_RUB дают null. */
export function parseRub(value: string): number | null {
  const digits = value.replace(/\s/g, '')
  if (!/^\d+$/.test(digits)) return null
  const rub = Number(digits)
  return rub > 0 && rub <= MAX_SALARY_RUB ? rub : null
}
