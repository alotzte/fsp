import type { MatchRead, SkillCheckRead, SkillCheckReadStatus } from '@/api/generated/model'
import { Badge } from '@/components/ui/badge'

const SKILL_STATUS: Record<
  SkillCheckReadStatus,
  { variant: 'default' | 'outline'; label: string; className?: string }
> = {
  verified: { variant: 'default', label: 'подтверждён тестом' },
  claimed: { variant: 'outline', label: 'заявлен, тестом не проверен' },
  missing: {
    variant: 'outline',
    label: 'нет в профиле',
    className: 'text-muted-foreground line-through',
  },
}

/** Навыки потребности с пометкой «подтверждён тестом / заявлен / нет в профиле». */
export function SkillChecks({ skills }: { skills: SkillCheckRead[] }) {
  if (skills.length === 0) return null
  return (
    <ul className="flex flex-wrap gap-1.5" aria-label="Навыки потребности">
      {skills.map((skill) => {
        const status = SKILL_STATUS[skill.status]
        return (
          <li key={skill.title}>
            <Badge
              variant={status.variant}
              className={status.className}
              title={`${skill.must_have ? 'Обязательный' : 'Желательный'}: ${status.label}`}
            >
              {skill.status === 'verified' && <span aria-hidden>✓</span>}
              {skill.title}
              <span className="sr-only">, {status.label}</span>
            </Badge>
          </li>
        )
      })}
    </ul>
  )
}

/** Почему кандидат на этой позиции: причины и вклад каждой составляющей в итоговый скор. */
export function MatchExplanation({
  match,
  detailed = false,
}: {
  match: MatchRead
  detailed?: boolean
}) {
  return (
    <div className="flex flex-col gap-3">
      <SkillChecks skills={match.skills} />
      <ul className="flex flex-col gap-1 text-sm">
        {match.reasons.map((reason) => (
          <li key={reason} className="flex gap-2">
            <span aria-hidden className="text-primary">
              •
            </span>
            {reason}
          </li>
        ))}
      </ul>
      {detailed && (
        <dl className="grid grid-cols-[auto_1fr_auto] items-center gap-x-3 gap-y-2 text-sm">
          {match.contributions.map((c) => (
            <div key={c.key} className="contents">
              <dt className="text-muted-foreground">{c.title}</dt>
              <dd className="h-2 overflow-hidden rounded-full bg-muted" aria-hidden>
                <span className="block h-full bg-primary" style={{ width: `${100 * c.value}%` }} />
              </dd>
              <dd className="font-mono text-xs text-muted-foreground">
                {Math.round(100 * c.value)}% × {c.weight}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  )
}
