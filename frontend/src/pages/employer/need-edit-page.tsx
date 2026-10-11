import { useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router'

import {
  getGetHiringNeedQueryKey,
  getListHiringNeedsQueryKey,
  getSearchCandidatesQueryKey,
  useCreateHiringNeed,
  useGetHiringNeed,
  useListSentInvitations,
  useUpdateHiringNeed,
} from '@/api/generated/employer/employer'
import type { HiringNeedRead } from '@/api/generated/model'
import { ErrorState } from '@/components/error-state'
import { PageLoader } from '@/components/page-loader'
import { NeedForm } from '@/features/hiring/need-form'
import { candidatesPath } from '@/features/hiring/paths'
import { SentInvitation } from '@/features/invitations/sent-invitation'

export function NeedEditPage() {
  const { needId } = useParams()
  return (
    <div className="flex max-w-3xl flex-col gap-4">
      <Link to="/employer" className="text-sm text-primary hover:underline">
        ← К потребностям
      </Link>
      <h2 className="text-xl font-semibold">{needId ? 'Потребность' : 'Новая потребность'}</h2>
      {needId ? <EditNeed needId={needId} /> : <CreateNeed />}
    </div>
  )
}

function useOnSaved() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  return (need: HiringNeedRead) => {
    void queryClient.invalidateQueries({ queryKey: getListHiringNeedsQueryKey() })
    // Подборка считается по потребности: после правки (грейд, навыки) прежняя выдача неверна.
    void queryClient.invalidateQueries({ queryKey: getSearchCandidatesQueryKey() })
    queryClient.setQueryData(getGetHiringNeedQueryKey(need.id), need)
    void navigate(candidatesPath({ need: need.id }))
  }
}

function CreateNeed() {
  const create = useCreateHiringNeed({ mutation: { onSuccess: useOnSaved() } })
  return (
    <NeedForm
      submitLabel="Сохранить и показать подборку"
      isPending={create.isPending}
      error={create.error}
      onSubmit={(data) => create.mutate({ data })}
    />
  )
}

function EditNeed({ needId }: { needId: string }) {
  const need = useGetHiringNeed(needId)
  const update = useUpdateHiringNeed({ mutation: { onSuccess: useOnSaved() } })
  if (need.isPending) return <PageLoader />
  if (need.isError) return <ErrorState message={need.error.message} />
  return (
    <>
      <NeedForm
        need={need.data}
        submitLabel="Сохранить и показать подборку"
        isPending={update.isPending}
        error={update.error}
        onSubmit={(data) => update.mutate({ needId, data })}
      />
      {need.data.published_at && <Applications needId={needId} />}
    </>
  )
}

/** Отклики на опубликованную вакансию: кандидаты пришли сами, их контакты уже открыты. */
function Applications({ needId }: { needId: string }) {
  const invitations = useListSentInvitations()
  if (invitations.isPending) return <PageLoader />
  if (invitations.isError) return <ErrorState message={invitations.error.message} />
  const applications = invitations.data.filter(
    (i) => i.direction === 'candidate' && i.need_id === needId,
  )
  return (
    <section className="flex flex-col gap-3">
      <h3 className="text-lg font-semibold">Отклики на вакансию</h3>
      {applications.length === 0 && (
        <p className="text-sm text-muted-foreground">
          Пока никто не откликнулся. Вакансию видят кандидаты направления в своей ленте.
        </p>
      )}
      {applications.map((invitation) => (
        <SentInvitation key={invitation.id} invitation={invitation} />
      ))}
    </section>
  )
}
