import { useState } from 'react'
import { useSearchParams } from 'react-router'

import { useGetMyAssessment } from '@/api/generated/assessment/assessment'
import { useGetWeeklyCase } from '@/api/generated/cases/cases'

import {
  getDownloadMyProfilePdfUrl,
  useGetMyCandidateProfile,
  useGetMyEmployerView,
} from '@/api/generated/candidate/candidate'
import type { CandidateProfileRead } from '@/api/generated/model'
import { DownloadPdfButton } from '@/components/download-pdf-button'
import { ErrorState } from '@/components/error-state'
import { PageLoader } from '@/components/page-loader'
import { AssessmentPanel } from '@/features/assessment/assessment-panel'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { VacancyFeed } from '@/features/vacancies/vacancy-feed'
import { ConsentGate } from '@/features/candidate-profile/consent-gate'
import { isConsentActive } from '@/features/candidate-profile/consents'
import { DeleteProfileCard } from '@/features/candidate-profile/delete-profile-card'
import { ProfileForm } from '@/features/candidate-profile/profile-form'
import { PublicationCard } from '@/features/candidate-profile/publication-card'
import { CandidateSections, CategoryCard } from '@/features/candidates/candidate-sections'
import { WeeklyCaseCard } from '@/features/cases/weekly-case-card'
import { FspCard } from '@/features/fsp/fsp-card'
import { CandidateInvitations } from '@/features/invitations/candidate-invitations'
import { CountBadge } from '@/features/notifications/notifications'
import { useNotifications } from '@/features/notifications/use-notifications'

export function CandidateHomePage() {
  const profile = useGetMyCandidateProfile()

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold">Кабинет кандидата</h1>
      {profile.isPending && <PageLoader />}
      {profile.isError && <ErrorState message={profile.error.message} />}
      {profile.isSuccess &&
        (isConsentActive(profile.data.consents, 'data_processing') ? (
          <ProfileWorkspace profile={profile.data} />
        ) : (
          <ConsentGate />
        ))}
    </div>
  )
}

// Вкладка лежит в адресе (?tab=invitations): на неё ведёт ссылка из письма о приглашении.
const TABS = ['edit', 'assessment', 'case', 'invitations', 'vacancies', 'preview'] as const
type Tab = (typeof TABS)[number]

function isTab(value: string | null): value is Tab {
  return TABS.some((tab) => tab === value)
}

function ProfileWorkspace({ profile }: { profile: CandidateProfileRead }) {
  const [searchParams, setSearchParams] = useSearchParams()
  const requested = searchParams.get('tab')
  const notifications = useNotifications()
  const toAnswer = notifications?.invitations_to_answer ?? 0
  // Без вкладки в адресе открываем приглашения, если они ждут ответа: главное не прячем за
  // формой профиля. Решаем один раз: новое приглашение не должно уводить из формы.
  const [landing, setLanding] = useState<Tab | null>(null)
  if (landing === null && notifications) setLanding(toAnswer > 0 ? 'invitations' : 'edit')
  const tab = isTab(requested) ? requested : (landing ?? 'edit')
  // Подсказки «что сделать» на вкладках: из тех же запросов, что и сами вкладки (кэш общий).
  const assessment = useGetMyAssessment({ query: { enabled: profile.exists } })
  const weekly = useGetWeeklyCase({ query: { enabled: profile.exists } })
  const testHint = assessment.data && !assessment.data.category?.confirmed_grade
  const caseHint = weekly.data && weekly.data.response === null

  function selectTab(value: unknown) {
    // «edit» тоже пишем в адрес: без вкладки в адресе сработал бы landing и вернул на приглашения.
    setSearchParams(
      (params) => {
        params.set('tab', String(value))
        return params
      },
      { replace: true },
    )
  }

  return (
    <Tabs value={tab} onValueChange={selectTab}>
      <TabsList className="max-w-full flex-wrap justify-start group-data-horizontal/tabs:h-auto">
        <TabsTrigger value="edit">Профиль</TabsTrigger>
        <TabsTrigger value="assessment">
          Категория и тест
          {testHint && <TodoDot label="грейд не подтверждён" />}
        </TabsTrigger>
        <TabsTrigger value="case" disabled={!profile.exists}>
          Кейс недели
          {caseHint && <TodoDot label="кейс не решён" />}
        </TabsTrigger>
        <TabsTrigger value="invitations">
          Приглашения
          <CountBadge count={toAnswer} />
        </TabsTrigger>
        <TabsTrigger value="vacancies" disabled={!profile.exists}>
          Вакансии
        </TabsTrigger>
        <TabsTrigger value="preview" disabled={!profile.exists}>
          Как вас видят работодатели
        </TabsTrigger>
      </TabsList>
      {/* forceMount: форма профиля не размонтируется при переходе на другую вкладку, иначе
          несохранённые правки и черновик из резюме молча пропадали. */}
      <TabsContent value="edit" forceMount className="mt-4 data-[state=inactive]:hidden">
        <div className="grid items-start gap-4 lg:grid-cols-[1fr_320px]">
          {/* Без key: профиль удаляется отзывом согласия, форма и так монтируется заново, а key
              по exists стирал бы «Сохранено» после первого сохранения. */}
          <ProfileForm profile={profile} />
          <aside className="flex flex-col gap-4 lg:sticky lg:top-4">
            <PublicationCard profile={profile} />
            <FspCard profile={profile} />
            {profile.exists && <DeleteProfileCard />}
          </aside>
        </div>
      </TabsContent>
      <TabsContent value="assessment" className="mt-4">
        <AssessmentPanel profileSpecializationId={profile.specialization?.id ?? null} />
      </TabsContent>
      <TabsContent value="case" className="mt-4">
        <WeeklyCaseCard />
      </TabsContent>
      <TabsContent value="invitations" className="mt-4">
        <CandidateInvitations />
      </TabsContent>
      <TabsContent value="vacancies" className="mt-4">
        <VacancyFeed />
      </TabsContent>
      <TabsContent value="preview" className="mt-4 max-w-3xl">
        <EmployerPreview />
      </TabsContent>
    </Tabs>
  )
}

function EmployerPreview() {
  const view = useGetMyEmployerView()
  if (view.isPending) return <PageLoader />
  if (view.isError) return <ErrorState message={view.error.message} />
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-muted-foreground">
        Так профиль выглядит для работодателя, пока вы не приняли его приглашение: без ФИО,
        контактов и названий компаний.
      </p>
      <CategoryCard category={view.data.category} />
      <CandidateSections details={view.data} />
      <div className="flex flex-wrap items-center gap-3">
        <DownloadPdfButton apiPath={getDownloadMyProfilePdfUrl()} label="Скачать мой PDF-профиль" />
        <span className="text-xs text-muted-foreground">
          С ФИО и контактами, так его увидит работодатель после принятия приглашения.
        </span>
      </div>
    </div>
  )
}

/** Точка на вкладке: там есть что сделать. */
function TodoDot({ label }: { label: string }) {
  return (
    <span
      className="size-2 rounded-full bg-destructive"
      title={label}
      aria-label={label}
      role="img"
    />
  )
}
