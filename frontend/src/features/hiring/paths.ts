/** Фильтры подборки живут в адресе: их можно уточнять, вернуться назад и поделиться ссылкой. */
export interface CandidateFilters {
  need?: string
  specialization?: number
  grade?: number
  skills?: number[]
  confirmed?: boolean
  format?: string
  /** Только с достижениями ФСП. */
  fsp?: boolean
}

export function filtersToParams(filters: CandidateFilters): URLSearchParams {
  const params = new URLSearchParams()
  if (filters.need) params.set('need', filters.need)
  if (filters.specialization) params.set('specialization', String(filters.specialization))
  if (filters.grade) params.set('grade', String(filters.grade))
  if (filters.skills?.length) params.set('skills', filters.skills.join(','))
  if (filters.confirmed) params.set('confirmed', '1')
  if (filters.format) params.set('format', filters.format)
  if (filters.fsp) params.set('fsp', '1')
  return params
}

export function candidatesPath(filters: CandidateFilters = {}): string {
  const query = filtersToParams(filters).toString()
  return query ? `/employer/candidates?${query}` : '/employer/candidates'
}

export function parseCandidateFilters(params: URLSearchParams): CandidateFilters {
  const number = (key: string) => {
    const value = Number(params.get(key))
    return Number.isInteger(value) && value > 0 ? value : undefined
  }
  return {
    need: params.get('need') ?? undefined,
    specialization: number('specialization'),
    grade: number('grade'),
    skills: (params.get('skills') ?? '')
      .split(',')
      .map(Number)
      .filter((id) => Number.isInteger(id) && id > 0),
    confirmed: params.get('confirmed') === '1',
    format: params.get('format') ?? undefined,
    fsp: params.get('fsp') === '1',
  }
}

export function candidatePath(candidateNumber: number, needId?: string): string {
  return `/employer/candidates/${candidateNumber}${needId ? `?need=${needId}` : ''}`
}
