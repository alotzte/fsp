import type { MatchRead } from '@/api/generated/model'

/** Соответствие в процентах: скор это взвешенная сумма вкладов от 0 до 1. */
export function matchPercent(match: MatchRead): number {
  return Math.round(100 * match.score)
}
