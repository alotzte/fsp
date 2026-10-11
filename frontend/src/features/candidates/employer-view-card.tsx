import type { CandidateEmployerView } from '@/api/generated/model'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  experienceFact,
  formatPeriod,
  PROFILE_SECTION_LABELS,
  WORK_FORMAT_LABELS,
} from '@/features/candidate-profile/format'

/**
 * Профиль кандидата глазами работодателя до принятия приглашения.
 * Данные приходят уже обезличенными с бэка (CandidateEmployerView), здесь только отрисовка.
 */
export function EmployerViewCard({ view }: { view: CandidateEmployerView }) {
  const facts = [
    view.specialization?.title,
    view.city,
    view.work_formats.map((format) => WORK_FORMAT_LABELS[format]).join(', '),
    experienceFact(view.total_experience_months),
  ].filter(Boolean)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-xl">Кандидат №{view.candidate_number}</CardTitle>
        <CardDescription>{facts.join(' · ')}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        {view.technologies.length > 0 && (
          <section className="flex flex-col gap-2">
            <h3 className="text-sm font-medium text-muted-foreground">Технологии</h3>
            <div className="flex flex-wrap gap-2">
              {view.technologies.map((title) => (
                <Badge key={title} variant="secondary">
                  {title}
                </Badge>
              ))}
            </div>
          </section>
        )}
        {view.soft_skills.length > 0 && (
          <section className="flex flex-col gap-2">
            <h3 className="text-sm font-medium text-muted-foreground">Софт-скиллы</h3>
            <div className="flex flex-wrap gap-2">
              {view.soft_skills.map((title) => (
                <Badge key={title} variant="outline">
                  {title}
                </Badge>
              ))}
            </div>
          </section>
        )}
        {view.about && (
          <section className="flex flex-col gap-2">
            <h3 className="text-sm font-medium text-muted-foreground">О себе</h3>
            <p className="[overflow-wrap:anywhere] whitespace-pre-line">{view.about}</p>
          </section>
        )}
        {view.experience.length > 0 && (
          <section className="flex flex-col gap-3">
            <h3 className="text-sm font-medium text-muted-foreground">Опыт</h3>
            <ul className="flex flex-col gap-4">
              {view.experience.map((entry) => (
                <li key={`${entry.position}-${entry.started_on}`} className="flex flex-col gap-1">
                  <span className="font-medium">
                    {entry.position}
                    {/* Название компании приходит, только когда кандидат открыл контакты. */}
                    {entry.company_name && `, ${entry.company_name}`}
                  </span>
                  <span className="text-sm text-muted-foreground">
                    {formatPeriod(entry.started_on, entry.ended_on)}
                  </span>
                  {entry.description && (
                    <p className="text-sm [overflow-wrap:anywhere] whitespace-pre-line">
                      {entry.description}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          </section>
        )}
        {view.education.length > 0 && (
          <section className="flex flex-col gap-2">
            <h3 className="text-sm font-medium text-muted-foreground">Образование</h3>
            <ul className="flex flex-col gap-1">
              {view.education.map((entry) => (
                <li key={`${entry.institution}-${entry.graduation_year ?? ''}`}>
                  {entry.institution}
                  {entry.specialty && `, ${entry.specialty}`}
                  {entry.graduation_year && `, ${entry.graduation_year}`}
                </li>
              ))}
            </ul>
          </section>
        )}
        {view.hidden_sections.length > 0 && (
          <p className="text-sm text-muted-foreground">
            Кандидат открывает после принятия приглашения:{' '}
            {view.hidden_sections.map((section) => PROFILE_SECTION_LABELS[section]).join(', ')}.
          </p>
        )}
      </CardContent>
    </Card>
  )
}
