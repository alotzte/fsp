import { createBrowserRouter } from 'react-router'

import { AppShell } from '@/components/layout/app-shell'
import { RequireRole } from '@/features/auth/require-role'
import { CompanyPanel } from '@/features/companies/company-panel'
import { EmployerLayout } from '@/features/employer/employer-layout'
import { AssessmentAttemptPage } from '@/pages/candidate/assessment-attempt-page'
import { CandidateHomePage } from '@/pages/candidate/candidate-home-page'
import { CandidatesPage } from '@/pages/employer/candidates-page'
import { EmployerCandidatePage } from '@/pages/employer/employer-candidate-page'
import { InvitationsPage } from '@/pages/employer/invitations-page'
import { NeedEditPage } from '@/pages/employer/need-edit-page'
import { NeedsPage } from '@/pages/employer/needs-page'
import { HomePage } from '@/pages/home-page'
import { JoinCompanyPage } from '@/pages/join-company-page'
import { MessagesPage } from '@/pages/messages-page'
import { NotFoundPage } from '@/pages/not-found-page'
import { OnboardingPage } from '@/pages/onboarding-page'
import { RouteErrorPage } from '@/pages/route-error-page'

export const router = createBrowserRouter(
  [
    {
      element: <AppShell />,
      errorElement: <RouteErrorPage />,
      children: [
        { index: true, element: <HomePage /> },
        { path: 'onboarding', element: <OnboardingPage /> },
        // Путь /join/:token зашит в ссылки-приглашения на бэке (INVITE_FRONTEND_PATH).
        { path: 'join/:token', element: <JoinCompanyPage /> },
        {
          element: <RequireRole />,
          children: [
            { path: 'messages', element: <MessagesPage /> },
            // Ссылки «Открыть переписку» из карточек приглашений.
            { path: 'messages/:invitationId', element: <MessagesPage /> },
          ],
        },
        {
          element: <RequireRole role="candidate" />,
          children: [
            { path: 'candidate', element: <CandidateHomePage /> },
            // Ссылки на этот путь строит attemptPath (features/assessment/format.ts).
            { path: 'candidate/assessment/:attemptId', element: <AssessmentAttemptPage /> },
          ],
        },
        {
          element: <RequireRole role="employer" />,
          children: [
            {
              path: 'employer',
              element: <EmployerLayout />,
              children: [
                { index: true, element: <NeedsPage /> },
                { path: 'needs/new', element: <NeedEditPage /> },
                { path: 'needs/:needId', element: <NeedEditPage /> },
                // Ссылки на подборку строит candidatesPath (features/hiring/paths.ts).
                { path: 'candidates', element: <CandidatesPage /> },
                { path: 'candidates/:candidateNumber', element: <EmployerCandidatePage /> },
                { path: 'invitations', element: <InvitationsPage /> },
                { path: 'company', element: <CompanyPanel /> },
              ],
            },
          ],
        },
        { path: '*', element: <NotFoundPage /> },
      ],
    },
  ],
  { basename: import.meta.env.BASE_URL },
)
