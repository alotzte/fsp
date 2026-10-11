import { XIcon } from 'lucide-react'
import { useId, useMemo, useState } from 'react'

import { useListSkills } from '@/api/generated/dictionaries/dictionaries'
import type { SkillDictionaryRead, SkillKind } from '@/api/generated/model'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import type { SkillValue } from '@/features/candidate-profile/form-schema'

const MAX_SUGGESTIONS = 8
const CUSTOM_TITLE_MAX = 64

const normalize = (value: string) => value.trim().replace(/\s+/g, ' ').toLocaleLowerCase('ru')

function matchesQuery(skill: SkillDictionaryRead, query: string): boolean {
  return [skill.title, ...skill.aliases].some((name) => normalize(name).includes(query))
}

function isSameSkill(a: SkillValue, b: SkillValue): boolean {
  return a.skill_id !== null || b.skill_id !== null
    ? a.skill_id === b.skill_id
    : normalize(a.title) === normalize(b.title)
}

interface SkillsInputProps {
  kind: SkillKind
  label: string
  placeholder: string
  value: SkillValue[]
  onChange: (value: SkillValue[]) => void
  /** Только навыки из справочника, без своих тегов (например, в потребности работодателя). */
  dictionaryOnly?: boolean
}

/**
 * Навыки из справочника плюс свои теги. Совпадение со справочником ищется и по синонимам
 * («js» → JavaScript); окончательно своё название с ним сопоставит бэк.
 */
export function SkillsInput({
  kind,
  label,
  placeholder,
  value,
  onChange,
  dictionaryOnly = false,
}: SkillsInputProps) {
  const inputId = useId()
  const [query, setQuery] = useState('')
  const [isFocused, setIsFocused] = useState(false)
  const dictionary = useListSkills({ kind })
  const normalizedQuery = normalize(query)

  const suggestions = useMemo(() => {
    if (!normalizedQuery || !dictionary.data) return []
    return dictionary.data
      .filter((skill) => matchesQuery(skill, normalizedQuery))
      .filter((skill) => !value.some((selected) => selected.skill_id === skill.id))
      .slice(0, MAX_SUGGESTIONS)
  }, [dictionary.data, normalizedQuery, value])

  function add(skill: SkillValue) {
    if (!value.some((selected) => isSameSkill(selected, skill))) onChange([...value, skill])
    setQuery('')
  }

  function addTyped() {
    if (!normalizedQuery) return
    const exact = dictionary.data?.find((skill) =>
      [skill.title, ...skill.aliases].some((name) => normalize(name) === normalizedQuery),
    )
    if (exact) add({ skill_id: exact.id, title: exact.title })
    else if (!dictionaryOnly) add({ skill_id: null, title: query.trim().replace(/\s+/g, ' ') })
  }

  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={inputId} className="text-sm font-medium">
        {label}
      </label>
      {value.length > 0 && (
        <ul className="flex flex-wrap gap-2" aria-label={label}>
          {value.map((skill) => (
            <li key={skill.skill_id ?? `custom:${skill.title}`}>
              <Badge
                variant={skill.skill_id !== null ? 'secondary' : 'outline'}
                className="gap-1 pr-1"
              >
                {skill.title}
                <button
                  type="button"
                  className="rounded-full p-0.5 hover:bg-foreground/10"
                  aria-label={`Удалить ${skill.title}`}
                  onClick={() =>
                    onChange(value.filter((selected) => !isSameSkill(selected, skill)))
                  }
                >
                  <XIcon className="size-3" />
                </button>
              </Badge>
            </li>
          ))}
        </ul>
      )}
      <div className="relative">
        <Input
          id={inputId}
          value={query}
          maxLength={CUSTOM_TITLE_MAX}
          placeholder={placeholder}
          autoComplete="off"
          onChange={(event) => setQuery(event.target.value)}
          onFocus={() => setIsFocused(true)}
          onBlur={() => setIsFocused(false)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              // Enter внутри формы иначе отправил бы её целиком.
              event.preventDefault()
              addTyped()
            }
          }}
        />
        {isFocused && normalizedQuery && (
          <div className="absolute inset-x-0 top-full z-10 mt-1 overflow-hidden rounded-md border bg-popover text-sm shadow-md">
            {suggestions.map((skill) => (
              <button
                key={skill.id}
                type="button"
                className="block w-full px-3 py-2 text-left hover:bg-accent hover:text-accent-foreground"
                // mousedown, а не click: иначе поле теряет фокус раньше, чем сработает выбор.
                onMouseDown={(event) => {
                  event.preventDefault()
                  add({ skill_id: skill.id, title: skill.title })
                }}
              >
                {skill.title}
              </button>
            ))}
            {dictionaryOnly ? (
              suggestions.length === 0 && (
                <p className="px-3 py-2 text-muted-foreground">Такого навыка нет в справочнике</p>
              )
            ) : (
              <p className="border-t px-3 py-2 text-muted-foreground">
                Enter: добавить «{query.trim()}»{suggestions.length === 0 && ' как свой навык'}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
