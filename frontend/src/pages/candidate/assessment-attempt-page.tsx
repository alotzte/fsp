import { useQueryClient } from '@tanstack/react-query'
import { type SyntheticEvent, useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router'

import {
  getGetAssessmentAttemptQueryKey,
  getGetMyAssessmentQueryKey,
  useFinishAssessmentAttempt,
  useGetAssessmentAttempt,
  useSaveAssessmentAnswer,
} from '@/api/generated/assessment/assessment'
import type { AttemptItemRead, AttemptRead, AttemptResultRead } from '@/api/generated/model'
import { ErrorState } from '@/components/error-state'
import { PageLoader } from '@/components/page-loader'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { BORDERLINE_AGREEMENT, formatCountdown, formatPercent } from '@/features/assessment/format'
import { cn } from '@/lib/utils'

export function AssessmentAttemptPage() {
  const { attemptId = '' } = useParams()
  const attempt = useGetAssessmentAttempt(attemptId)

  return (
    <div className="flex flex-col gap-6">
      <Link to="/candidate" className="text-sm text-primary hover:underline">
        ← В кабинет
      </Link>
      {attempt.isPending && <PageLoader />}
      {attempt.isError && <ErrorState message={attempt.error.message} />}
      {attempt.isSuccess &&
        (attempt.data.result ? (
          <AttemptResult attempt={attempt.data} result={attempt.data.result} />
        ) : (
          <AttemptRunner attempt={attempt.data} />
        ))}
    </div>
  )
}

// Условие, код и варианты нельзя выделить и скопировать: так задание не уходит одним движением
// в чат или интерпретатор. Это барьер, а не защита (остаются скриншот и devtools); от утечки
// защищают семейства заданий: у каждого кандидата свой экземпляр. Поле ответа не трогаем.
function blockCopy(event: SyntheticEvent) {
  if (!(event.target instanceof HTMLInputElement)) event.preventDefault()
}

const noCopyHandlers = {
  onCopy: blockCopy,
  onCut: blockCopy,
  onContextMenu: blockCopy,
  onDragStart: blockCopy,
}

const TIME_UP_POLL_MS = 5000
const TEXT_AUTOSAVE_MS = 800

function useSecondsLeft(deadline: string): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])
  return (new Date(deadline).getTime() - now) / 1000
}

function AttemptRunner({ attempt }: { attempt: AttemptRead }) {
  const queryClient = useQueryClient()
  const [current, setCurrent] = useState(0)
  // Локальные ответы: интерфейс не ждёт сохранения, сервер получает их в фоне.
  const [answers, setAnswers] = useState<Record<number, string | null>>(() =>
    Object.fromEntries(attempt.items.map((item) => [item.position, item.response])),
  )
  const secondsLeft = useSecondsLeft(attempt.deadline_at)
  const refresh = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: getGetAssessmentAttemptQueryKey(attempt.id) })
    void queryClient.invalidateQueries({ queryKey: getGetMyAssessmentQueryKey() })
  }, [queryClient, attempt.id])
  const save = useSaveAssessmentAnswer()
  const finish = useFinishAssessmentAttempt({ mutation: { onSuccess: refresh } })
  const timeIsUp = secondsLeft <= 0
  // Продление у порога: после «Завершить» бэк добавил задания, переходим к первому новому.
  const [seenItems, setSeenItems] = useState(attempt.items.length)
  if (attempt.items.length > seenItems) {
    setSeenItems(attempt.items.length)
    setCurrent(seenItems)
  }

  // Время вышло: бэк сам завершает просроченную попытку при чтении, но с запасом в полминуты
  // на последние ответы, поэтому спрашиваем, пока не придёт результат, а не один раз.
  useEffect(() => {
    if (!timeIsUp) return
    refresh()
    const id = setInterval(refresh, TIME_UP_POLL_MS)
    return () => clearInterval(id)
  }, [timeIsUp, refresh])

  const item = attempt.items[current]
  const unanswered = attempt.items.filter((i) => !answers[i.position]).length
  const answer = (position: number, response: string | null) => {
    setAnswers((prev) => ({ ...prev, [position]: response }))
    save.mutate({ attemptId: attempt.id, position, data: { response } })
  }

  return (
    <div className="grid items-start gap-4 lg:grid-cols-[1fr_280px]">
      <Card className="select-none" {...noCopyHandlers}>
        <CardHeader>
          <CardDescription>
            Задание {current + 1} из {attempt.items.length} · {item.competency_title}
          </CardDescription>
          <CardTitle className="text-lg leading-snug font-medium">{item.prompt}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-6">
          {item.code && (
            <pre className="overflow-x-auto rounded-md bg-muted p-4 font-mono text-sm leading-relaxed">
              {item.code}
            </pre>
          )}
          <ItemAnswer
            key={item.position}
            item={item}
            value={answers[item.position] ?? null}
            disabled={timeIsUp}
            onAnswer={(response) => answer(item.position, response)}
          />
          {save.isError && (
            <Alert variant="destructive">
              <AlertDescription>Ответ не сохранился: {save.error.message}</AlertDescription>
            </Alert>
          )}
          <div className="flex justify-between gap-2">
            <Button
              variant="outline"
              disabled={current === 0}
              onClick={() => setCurrent((c) => c - 1)}
            >
              Назад
            </Button>
            {current < attempt.items.length - 1 && (
              <Button onClick={() => setCurrent((c) => c + 1)}>Дальше</Button>
            )}
          </div>
        </CardContent>
      </Card>

      <aside className="flex flex-col gap-4 lg:sticky lg:top-4">
        <Card>
          <CardHeader>
            <CardDescription>
              {attempt.grade.title} · {attempt.specialization.title}
              {attempt.is_express && ' · экспресс-тест'}
            </CardDescription>
            <CardTitle
              className={cn('font-heading text-3xl', secondsLeft < 60 && 'text-destructive')}
              aria-live="off"
            >
              {formatCountdown(secondsLeft)}
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {attempt.extensions > 0 && (
              <Alert>
                <AlertDescription>
                  Результат оказался у самой границы грейда, поэтому мы добавили задания: по ним
                  решение будет точнее. Время на них уже добавлено.
                </AlertDescription>
              </Alert>
            )}
            <nav aria-label="Задания" className="grid grid-cols-5 gap-2">
              {attempt.items.map((i, index) => (
                <Button
                  key={i.position}
                  size="sm"
                  variant={
                    index === current ? 'default' : answers[i.position] ? 'secondary' : 'outline'
                  }
                  aria-current={index === current ? 'step' : undefined}
                  aria-label={`Задание ${index + 1}${answers[i.position] ? ', есть ответ' : ''}`}
                  onClick={() => setCurrent(index)}
                >
                  {index + 1}
                </Button>
              ))}
            </nav>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button disabled={finish.isPending || timeIsUp}>Завершить тест</Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Завершить тест?</AlertDialogTitle>
                  <AlertDialogDescription>
                    {unanswered > 0
                      ? `Без ответа осталось заданий: ${unanswered}. Они будут засчитаны как неверные.`
                      : 'Ответы на все задания даны.'}{' '}
                    Если результат окажется у самой границы грейда, мы добавим несколько заданий,
                    чтобы решение было точнее.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Вернуться к заданиям</AlertDialogCancel>
                  <AlertDialogAction
                    onClick={() =>
                      finish.mutate({
                        attemptId: attempt.id,
                        params: { seen_items: attempt.items.length },
                      })
                    }
                  >
                    Завершить
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
            {finish.isError && (
              <Alert variant="destructive">
                <AlertDescription>{finish.error.message}</AlertDescription>
              </Alert>
            )}
            {timeIsUp && (
              <p className="text-sm text-muted-foreground">Время вышло, подводим итог...</p>
            )}
          </CardContent>
        </Card>
      </aside>
    </div>
  )
}

function ItemAnswer({
  item,
  value,
  disabled,
  onAnswer,
}: {
  item: AttemptItemRead
  value: string | null
  disabled: boolean
  onAnswer: (response: string | null) => void
}) {
  const [draft, setDraft] = useState(value ?? '')
  const commit = () => {
    const trimmed = draft.trim()
    if (trimmed !== (value ?? '')) onAnswer(trimmed || null)
  }
  // Автосохранение через паузу в наборе: иначе ответ, набранный перед перезагрузкой или
  // закрытием вкладки, терялся. Ref, потому что родитель перерисовывается каждую секунду
  // (таймер), и новый commit на каждый рендер сбрасывал бы отсрочку.
  const commitRef = useRef(commit)
  useEffect(() => {
    commitRef.current = commit
  })
  useEffect(() => {
    if (item.kind !== 'text') return
    const id = setTimeout(() => commitRef.current(), TEXT_AUTOSAVE_MS)
    return () => clearTimeout(id)
  }, [draft, item.kind])

  if (item.kind === 'text') {
    return (
      <div className="flex flex-col gap-2">
        <Input
          aria-label="Ответ"
          value={draft}
          disabled={disabled}
          maxLength={500}
          placeholder="Ваш ответ"
          className="font-mono select-text"
          onChange={(event) => setDraft(event.target.value)}
          onBlur={commit}
          onKeyDown={(event) => event.key === 'Enter' && commit()}
        />
        <span className="text-xs text-muted-foreground">
          Регистр и лишние пробелы не важны. Ответ сохраняется сам, пока вы печатаете.
        </span>
      </div>
    )
  }

  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="sr-only">Варианты ответа</legend>
      {item.options.map((option) => (
        <label
          key={option}
          className={cn(
            'flex cursor-pointer items-start gap-3 rounded-md border p-3 hover:bg-muted/50',
            value === option && 'border-primary bg-accent',
          )}
        >
          <input
            type="radio"
            name={`item-${item.position}`}
            className="mt-1 accent-primary"
            checked={value === option}
            disabled={disabled}
            onChange={() => onAnswer(option)}
          />
          <span className="[overflow-wrap:anywhere] whitespace-pre-line">{option}</span>
        </label>
      ))}
    </fieldset>
  )
}

function AttemptResult({ attempt, result }: { attempt: AttemptRead; result: AttemptResultRead }) {
  const estimated = result.estimated_grade
  return (
    <Card className="max-w-3xl">
      <CardHeader>
        <CardDescription>
          {attempt.is_express ? 'Экспресс-тест' : 'Тест'} на {attempt.grade.title} ·{' '}
          {attempt.specialization.title}
        </CardDescription>
        <CardTitle className="flex flex-wrap items-center gap-3 text-2xl">
          {result.passed ? `Грейд ${attempt.grade.title} подтверждён` : 'Грейд не подтверждён'}
          <Badge variant={result.passed ? 'default' : 'outline'}>
            {result.correct} из {result.total}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        <p>
          {result.passed
            ? estimated && estimated.level > attempt.grade.level
              ? `Результат уверенный: уровень ближе к грейду ${estimated.title}. В кабинете можно сразу пройти тест на следующий грейд.`
              : 'Категория обновлена: работодатели видят подтверждённый грейд.'
            : `${estimated ? `По результату уровень ближе к грейду ${estimated.title}. ` : ''}Что можно пройти дальше и когда, смотрите в кабинете.`}
        </p>
        {result.retest_agreement !== null && (
          <section className="flex flex-col gap-1">
            <h3 className="text-sm font-medium text-muted-foreground">Устойчивость результата</h3>
            <p className="flex flex-wrap items-center gap-2">
              <span className="font-heading text-2xl">
                {formatPercent(result.retest_agreement)}
              </span>
              {result.retest_agreement < BORDERLINE_AGREEMENT && (
                <Badge variant="outline">у границы грейда</Badge>
              )}
            </p>
            <p className="text-sm text-muted-foreground">
              С такой вероятностью повторная попытка на этот грейд даст то же решение.
              {result.retest_agreement < BORDERLINE_AGREEMENT &&
                ' Ваш уровень у самой границы грейда: здесь любой тест близок к монетке, и повтор может дать другой результат.'}
            </p>
          </section>
        )}
        <section className="flex flex-col gap-3">
          <h3 className="text-sm font-medium text-muted-foreground">По компетенциям</h3>
          <ul className="flex flex-col gap-3">
            {result.competencies.map((c) => (
              <li key={c.title} className="flex flex-col gap-1">
                <span className="flex justify-between text-sm">
                  {c.title}
                  <span className="font-mono">
                    {c.correct}/{c.total}
                  </span>
                </span>
                <span className="h-2 overflow-hidden rounded-full bg-muted">
                  <span
                    className="block h-full bg-primary"
                    style={{ width: `${(100 * c.correct) / c.total}%` }}
                  />
                </span>
              </li>
            ))}
          </ul>
        </section>
        <p className="text-sm text-muted-foreground">
          Правильные ответы не показываем, чтобы тест не превращался в шпаргалку.
        </p>
        <Button asChild className="self-start">
          <Link to="/candidate">В кабинет</Link>
        </Button>
      </CardContent>
    </Card>
  )
}
