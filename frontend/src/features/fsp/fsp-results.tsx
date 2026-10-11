import type {
  FspAward,
  FspDiscipline,
  FspRankRead,
  FspResultRead,
  FspSportRank,
} from '@/api/generated/model'
import { Badge } from '@/components/ui/badge'
import { formatDate } from '@/features/assessment/format'

const AWARD_LABELS: Record<FspAward, string> = {
  winner: 'победитель',
  prize: 'призёр',
  finalist: 'финалист',
  participant: 'участник',
}

const DISCIPLINE_LABELS: Record<FspDiscipline, string> = {
  algorithmic: 'алгоритмическое программирование',
  product: 'продуктовое программирование',
  infosec: 'программирование систем ИБ',
  robotics: 'программирование робототехники',
  uas: 'программирование БАС',
}

const SPORT_RANK_LABELS: Record<FspSportRank, string> = {
  third: 'III спортивный разряд',
  second: 'II спортивный разряд',
  first: 'I спортивный разряд',
  cms: 'кандидат в мастера спорта',
  ms: 'мастер спорта',
}

/** Разряд или звание по реестру ФСП. На позицию в подборке не влияет: его дают те же результаты. */
export function FspSportRankLine({ rank }: { rank: FspRankRead }) {
  return (
    <p className="flex flex-wrap items-center gap-2 text-sm">
      <Badge variant="secondary">{SPORT_RANK_LABELS[rank.rank]}</Badge>
      <span className="text-muted-foreground">
        спортивное программирование, с {formatDate(rank.assigned_on)}
      </span>
    </p>
  )
}

/** Результаты из реестра ФСП: проверенные данные, а не самоописание кандидата. */
export function FspResults({ results }: { results: FspResultRead[] }) {
  return (
    <ul className="flex flex-col gap-3">
      {results.map((r) => (
        <li
          key={`${r.event_title}-${r.discipline}-${r.starts_on}`}
          className="flex flex-col gap-1 text-sm"
        >
          <span className="flex flex-wrap items-center gap-2 font-medium">
            {r.event_title}
            <Badge variant={r.award === 'participant' ? 'outline' : 'default'}>
              {AWARD_LABELS[r.award]}
              {r.place !== null && `, ${r.place} место`}
            </Badge>
          </span>
          <span className="text-muted-foreground">
            {DISCIPLINE_LABELS[r.discipline]} · {formatDate(r.starts_on)}
            {r.team_name && ` · команда «${r.team_name}»`}
            {r.ekp_number && ` · № ЕКП ${r.ekp_number}`}
          </span>
        </li>
      ))}
    </ul>
  )
}
