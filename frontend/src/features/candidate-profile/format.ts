import type { ProfileSection, WorkFormat } from '@/api/generated/model'

export const WORK_FORMAT_LABELS: Record<WorkFormat, string> = {
  office: 'Офис',
  hybrid: 'Гибрид',
  remote: 'Удалёнка',
}

export const WORK_FORMATS = Object.keys(WORK_FORMAT_LABELS) as WorkFormat[]

/** Разделы, которые можно скрыть до принятия приглашения (ProfileSection на бэке). */
export const PROFILE_SECTION_LABELS: Record<ProfileSection, string> = {
  about: 'О себе',
  experience: 'Опыт работы',
  education: 'Образование',
  soft_skills: 'Софт-скиллы',
}

export const PROFILE_SECTIONS = Object.keys(PROFILE_SECTION_LABELS) as ProfileSection[]

const MONTHS_IN_YEAR = 12
const plural = new Intl.PluralRules('ru-RU')
const YEAR_FORMS: Record<string, string> = { one: 'год', few: 'года', many: 'лет', other: 'года' }
const MONTH_FORMS: Record<string, string> = {
  one: 'месяц',
  few: 'месяца',
  many: 'месяцев',
  other: 'месяца',
}

/** 41 → «3 года 5 месяцев». */
export function formatExperience(totalMonths: number): string {
  if (totalMonths <= 0) return 'без опыта'
  const years = Math.floor(totalMonths / MONTHS_IN_YEAR)
  const months = totalMonths % MONTHS_IN_YEAR
  const parts = []
  if (years > 0) parts.push(`${years} ${YEAR_FORMS[plural.select(years)]}`)
  if (months > 0) parts.push(`${months} ${MONTH_FORMS[plural.select(months)]}`)
  return parts.join(' ')
}

const rubFormat = new Intl.NumberFormat('ru-RU', {
  style: 'currency',
  currency: 'RUB',
  maximumFractionDigits: 0,
})

export function formatRub(amount: number): string {
  return rubFormat.format(amount)
}

const monthFormat = new Intl.DateTimeFormat('ru-RU', { month: 'long', year: 'numeric' })

/** «2020-01-01» → «январь 2020 г.». Дату разбираем сами: new Date('2020-01-01') это UTC. */
export function formatMonth(isoDate: string): string {
  const [year, month] = isoDate.split('-').map(Number)
  return monthFormat.format(new Date(year, month - 1, 1))
}

export function formatPeriod(startedOn: string, endedOn: string | null): string {
  return `${formatMonth(startedOn)} - ${endedOn ? formatMonth(endedOn) : 'по настоящее время'}`
}

/** «опыт 3 года» или «без опыта» для краткой строки фактов о кандидате. */
export function experienceFact(totalMonths: number): string {
  return totalMonths > 0 ? `опыт ${formatExperience(totalMonths)}` : 'без опыта'
}
