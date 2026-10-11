/** Кейс из приглашения и решение кандидата: оно приходит вместе с принятием приглашения. */
export function CaseBlock({
  task,
  answer,
  answerTitle,
}: {
  task: string
  answer: string | null
  answerTitle: string
}) {
  return (
    <section className="flex flex-col gap-2 rounded-md border p-3 text-sm">
      <h3 className="font-medium">Кейс от компании</h3>
      <p className="[overflow-wrap:anywhere] whitespace-pre-line">{task}</p>
      {answer && (
        <>
          <h4 className="font-medium">{answerTitle}</h4>
          <p className="[overflow-wrap:anywhere] whitespace-pre-line">{answer}</p>
        </>
      )}
    </section>
  )
}
