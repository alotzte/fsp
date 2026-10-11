import { z } from 'zod'

import type {
  CandidateProfileInput,
  CandidateProfileRead,
  ResumeDraftRead,
  SkillRead,
  WorkFormat,
} from '@/api/generated/model'
import { WORK_FORMATS } from '@/features/candidate-profile/format'

// Ограничения повторяют CandidateProfileInput на бэке (backend/app/schemas/candidates.py):
// фронт ловит ошибки до отправки, бэк всё равно проверяет сам.
const NAME_MAX = 100
const SHORT_TEXT_MAX = 200
const LONG_TEXT_MAX = 3000
const CITY_MAX = 100
const INSTITUTION_MAX = 300
const MAX_SALARY_RUB = 10_000_000
const MIN_GRADUATION_YEAR = 1950
const MAX_YEARS_TO_GRADUATION = 10
const PHONE = /^\+?[0-9 ()-]{7,20}$/
const TELEGRAM = /^@?[A-Za-z0-9_]{5,32}$|^(https?:\/\/)?t\.me\/[A-Za-z0-9_]{5,32}\/?$/i
const MONTH = /^\d{4}-\d{2}$/

const required = (max: number) =>
  z.string().trim().min(1, 'Обязательное поле').max(max, `Максимум ${max} символов`)
const optional = (max: number) => z.string().trim().max(max, `Максимум ${max} символов`)

/** Необязательное целое из поля ввода: пустая строка значит «не указано». */
const optionalInteger = (min: number, max: number, message: string) =>
  z
    .string()
    .trim()
    .refine(
      (value) => value === '' || (/^\d+$/.test(value) && +value >= min && +value <= max),
      message,
    )

const skillSchema = z.object({ skill_id: z.number().nullable(), title: z.string() })

const experienceSchema = z
  .object({
    company_name: required(SHORT_TEXT_MAX),
    position: required(SHORT_TEXT_MAX),
    started_on: z.string().regex(MONTH, 'Укажите месяц начала'),
    // Пустая строка значит «работаю сейчас».
    ended_on: z.string().refine((value) => value === '' || MONTH.test(value), 'Укажите месяц'),
    description: optional(LONG_TEXT_MAX),
  })
  .refine((entry) => entry.ended_on === '' || entry.ended_on >= entry.started_on, {
    message: 'Окончание раньше начала',
    path: ['ended_on'],
  })

const latestGraduationYear = new Date().getFullYear() + MAX_YEARS_TO_GRADUATION

const educationSchema = z.object({
  institution: required(INSTITUTION_MAX),
  specialty: optional(INSTITUTION_MAX),
  graduation_year: optionalInteger(
    MIN_GRADUATION_YEAR,
    latestGraduationYear,
    `Год от ${MIN_GRADUATION_YEAR} до ${latestGraduationYear}`,
  ),
})

export const profileFormSchema = z.object({
  last_name: required(NAME_MAX),
  first_name: required(NAME_MAX),
  middle_name: optional(NAME_MAX),
  phone: z
    .string()
    .trim()
    .refine((value) => value === '' || PHONE.test(value), 'Цифры, пробелы, скобки и дефисы'),
  telegram: z
    .string()
    .trim()
    .refine(
      (value) => value === '' || TELEGRAM.test(value),
      'Ник: латиница, цифры и _, 5-32 символа',
    ),
  specialization_id: z.number().nullable(),
  work_formats: z.array(z.enum(WORK_FORMATS as [WorkFormat, ...WorkFormat[]])),
  city: optional(CITY_MAX),
  salary_expectation_rub: optionalInteger(1, MAX_SALARY_RUB, 'Сумма в рублях, без копеек'),
  about: optional(LONG_TEXT_MAX),
  technologies: z.array(skillSchema),
  soft_skills: z.array(skillSchema),
  experience: z.array(experienceSchema),
  education: z.array(educationSchema),
})

export type ProfileFormValues = z.infer<typeof profileFormSchema>
export type SkillValue = z.infer<typeof skillSchema>

const toSkillValue = (skill: SkillRead): SkillValue => ({
  skill_id: skill.skill_id,
  title: skill.title,
})
const toMonth = (isoDate: string) => isoDate.slice(0, 7)
const toFirstOfMonth = (month: string) => `${month}-01`
const toOptionalNumber = (value: string) => (value.trim() === '' ? null : Number(value))

export function toFormValues(profile: CandidateProfileRead): ProfileFormValues {
  return {
    last_name: profile.last_name,
    first_name: profile.first_name,
    middle_name: profile.middle_name,
    phone: profile.phone,
    telegram: profile.telegram,
    specialization_id: profile.specialization?.id ?? null,
    work_formats: profile.work_formats,
    city: profile.city,
    salary_expectation_rub: profile.salary_expectation_rub?.toString() ?? '',
    about: profile.about,
    technologies: profile.technologies.map(toSkillValue),
    soft_skills: profile.soft_skills.map(toSkillValue),
    experience: profile.experience.map((entry) => ({
      company_name: entry.company_name,
      position: entry.position,
      started_on: toMonth(entry.started_on),
      ended_on: entry.ended_on ? toMonth(entry.ended_on) : '',
      description: entry.description,
    })),
    education: profile.education.map((entry) => ({
      institution: entry.institution,
      specialty: entry.specialty,
      graduation_year: entry.graduation_year?.toString() ?? '',
    })),
  }
}

const toSkillInput = (skill: SkillValue) =>
  skill.skill_id !== null ? { skill_id: skill.skill_id } : { title: skill.title }

export function toPayload(values: ProfileFormValues): CandidateProfileInput {
  return {
    ...values,
    salary_expectation_rub: toOptionalNumber(values.salary_expectation_rub),
    technologies: values.technologies.map(toSkillInput),
    soft_skills: values.soft_skills.map(toSkillInput),
    experience: values.experience.map((entry) => ({
      ...entry,
      started_on: toFirstOfMonth(entry.started_on),
      ended_on: entry.ended_on ? toFirstOfMonth(entry.ended_on) : null,
    })),
    education: values.education.map((entry) => ({
      ...entry,
      graduation_year: toOptionalNumber(entry.graduation_year),
    })),
  }
}

/** Черновик из PDF-резюме поверх формы: заполняет только пустое, навыки и места работы
 * добавляет без дублей. Возвращает новые значения и что именно заполнено, для подсказки. */
export function mergeResumeDraft(
  values: ProfileFormValues,
  draft: ResumeDraftRead,
): { values: ProfileFormValues; filled: string[] } {
  const filled: string[] = []
  const next = { ...values }
  if (!values.phone && draft.phone) {
    next.phone = draft.phone
    filled.push('телефон')
  }
  if (!values.telegram && draft.telegram) {
    next.telegram = draft.telegram
    filled.push('Telegram')
  }
  if (values.specialization_id === null && draft.specialization) {
    next.specialization_id = draft.specialization.id
    filled.push(`специализация «${draft.specialization.title}»`)
  }
  const addSkills = (current: SkillValue[], found: SkillRead[], label: string) => {
    const known = new Set(current.map((skill) => skill.skill_id ?? skill.title.toLowerCase()))
    const added = found.filter((skill) => !known.has(skill.skill_id ?? skill.title.toLowerCase()))
    if (added.length > 0) filled.push(`${label}: ${added.length}`)
    return [...current, ...added.map(toSkillValue)]
  }
  next.technologies = addSkills(values.technologies, draft.technologies, 'технологии')
  next.soft_skills = addSkills(values.soft_skills, draft.soft_skills, 'софт-скиллы')
  const knownStarts = new Set(values.experience.map((entry) => entry.started_on))
  const jobs = draft.experience
    .filter((entry) => !knownStarts.has(toMonth(entry.started_on)))
    .map((entry) => ({
      company_name: entry.company_name,
      position: entry.position,
      started_on: toMonth(entry.started_on),
      ended_on: entry.ended_on ? toMonth(entry.ended_on) : '',
      description: entry.description,
    }))
  if (jobs.length > 0) filled.push(`места работы: ${jobs.length}`)
  next.experience = [...values.experience, ...jobs]
  return { values: next, filled }
}
