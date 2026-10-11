import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import {
  getGetWeeklyCaseQueryKey,
  useAnswerWeeklyCase,
  useGetWeeklyCase,
} from '@/api/generated/cases/cases'
import type { WeeklyCaseRead } from '@/api/generated/model'
import { PageLoader } from '@/components/page-loader'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { formatDate } from '@/features/assessment/format'
import { cn } from '@/lib/utils'

/** Кейс недели: короткое задание своего направления раз в неделю. Работодатели видят, сколько
 * кейсов кандидат решил за месяц; на грейд результат не влияет. */
export function WeeklyCaseCard() {
  const weekly = useGetWeeklyCase()

  if (weekly.isPending) return <PageLoader />
  if (weekly.isError) {
    return (
      <Card className="max-w-3xl">
        <CardHeader>
          <CardTitle>Кейс недели</CardTitle>
          <CardDescription>{weekly.error.message}</CardDescription>
        </CardHeader>
      </Card>
    )
  }
  return <WeeklyCase key={String(weekly.data.week)} item={weekly.data} />
}

function WeeklyCase({ item }: { item: WeeklyCaseRead }) {
  const queryClient = useQueryClient()
  const [response, setResponse] = useState('')
  const answer = useAnswerWeeklyCase({
    mutation: {
      onSuccess: (data) => queryClient.setQueryData(getGetWeeklyCaseQueryKey(), data),
    },
  })
  const answered = item.is_correct !== null

  return (
    <Card className="max-w-3xl">
      <CardHeader>
        <CardDescription>
          Кейс недели: {item.competency_title}. Следующий {formatDate(item.next_case_on)}
        </CardDescription>
        <CardTitle className="text-lg leading-snug font-medium">{item.prompt}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {item.code && (
          <pre className="overflow-x-auto rounded-md bg-muted p-4 font-mono text-sm leading-relaxed">
            {item.code}
          </pre>
        )}
        {answered ? (
          <div className="flex flex-col gap-2">
            <p className="flex flex-wrap items-center gap-2">
              Ваш ответ: <span className="font-mono">{item.response ?? '-'}</span>
              {item.is_correct ? <Badge>верно</Badge> : <Badge variant="outline">неверно</Badge>}
            </p>
            <p className="text-sm text-muted-foreground">
              Правильный ответ не показываем, чтобы кейсы не превращались в шпаргалку.
            </p>
          </div>
        ) : (
          <form
            className="flex flex-col gap-3"
            onSubmit={(event) => {
              event.preventDefault()
              if (response.trim()) answer.mutate({ data: { response: response.trim() } })
            }}
          >
            {item.kind === 'choice' ? (
              <fieldset className="flex flex-col gap-2">
                <legend className="sr-only">Варианты ответа</legend>
                {item.options.map((option) => (
                  <label
                    key={option}
                    className={cn(
                      'flex cursor-pointer items-start gap-3 rounded-md border p-3 hover:bg-muted/50',
                      response === option && 'border-primary bg-accent',
                    )}
                  >
                    <input
                      type="radio"
                      name="weekly-case"
                      className="mt-1 accent-primary"
                      checked={response === option}
                      onChange={() => setResponse(option)}
                    />
                    <span className="[overflow-wrap:anywhere] whitespace-pre-line">{option}</span>
                  </label>
                ))}
              </fieldset>
            ) : (
              <Input
                aria-label="Ответ"
                maxLength={500}
                value={response}
                placeholder="Ваш ответ"
                className="font-mono"
                onChange={(event) => setResponse(event.target.value)}
              />
            )}
            {answer.isError && (
              <Alert variant="destructive">
                <AlertDescription>{answer.error.message}</AlertDescription>
              </Alert>
            )}
            <Button
              type="submit"
              className="self-start"
              disabled={!response.trim() || answer.isPending}
            >
              Ответить
            </Button>
            <p className="text-sm text-muted-foreground">
              Ответить можно один раз. На грейд кейс не влияет: грейд меняет только тест.
            </p>
          </form>
        )}
        <p className="text-sm">
          Решено верно за 30 дней: <span className="font-medium">{item.solved_recently}</span>.
          Работодатели видят это в подборке как признак, что вы в форме.
        </p>
      </CardContent>
    </Card>
  )
}
