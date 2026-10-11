import { GlobeIcon, MailIcon, PhoneIcon } from 'lucide-react'
import { useState } from 'react'

import { useGetMyCompany } from '@/api/generated/companies/companies'
import type { CompanyRole } from '@/api/generated/model'
import { ErrorState } from '@/components/error-state'
import { PageLoader } from '@/components/page-loader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { AtsTokensCard } from '@/features/companies/ats-tokens-card'
import { CompanyEditForm } from '@/features/companies/company-edit-form'
import { CompanyLogo } from '@/features/companies/company-logo'
import { InviteLinkCard } from '@/features/companies/invite-link-card'
import { LogoUpload } from '@/features/companies/logo-upload'
import { TrustCard } from '@/features/companies/trust-card'

const COMPANY_ROLE_LABELS: Record<CompanyRole, string> = {
  owner: 'Владелец',
  recruiter: 'Рекрутер',
}

export function CompanyPanel() {
  const company = useGetMyCompany()
  const [isEditing, setIsEditing] = useState(false)

  if (company.isPending) return <PageLoader />
  if (company.isError) return <ErrorState message={company.error.message} />

  const details = company.data
  const isOwner = details.my_role === 'owner'
  const contacts = [
    details.website && { icon: GlobeIcon, text: details.website, href: details.website },
    details.contact_email && {
      icon: MailIcon,
      text: details.contact_email,
      href: `mailto:${details.contact_email}`,
    },
    details.contact_phone && {
      icon: PhoneIcon,
      text: details.contact_phone,
      href: `tel:${details.contact_phone}`,
    },
  ].filter((contact) => !!contact)

  return (
    <div className="grid items-start gap-4 lg:grid-cols-[2fr_1fr]">
      <div className="flex flex-col gap-4">
        <Card>
          <CardHeader className="flex flex-row items-start gap-4">
            <CompanyLogo logoUrl={details.logo_url} name={details.name} />
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              <CardTitle className="text-xl">{details.name}</CardTitle>
              {details.industry && <CardDescription>{details.industry.title}</CardDescription>}
            </div>
            {isOwner && !isEditing && (
              <Button variant="outline" onClick={() => setIsEditing(true)}>
                Редактировать
              </Button>
            )}
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {isEditing ? (
              <>
                <LogoUpload logoUrl={details.logo_url} companyName={details.name} />
                <CompanyEditForm company={details} onDone={() => setIsEditing(false)} />
              </>
            ) : (
              <>
                {details.description && (
                  <p className="[overflow-wrap:anywhere] whitespace-pre-line">
                    {details.description}
                  </p>
                )}
                {contacts.length > 0 && (
                  <ul className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
                    {contacts.map(({ icon: Icon, text, href }) => (
                      <li key={text} className="flex items-center gap-2">
                        <Icon className="size-4 text-muted-foreground" aria-hidden />
                        <a
                          href={href}
                          className="text-primary underline-offset-4 hover:underline"
                          target={href.startsWith('http') ? '_blank' : undefined}
                          rel="noreferrer"
                        >
                          {text}
                        </a>
                      </li>
                    ))}
                  </ul>
                )}
                {!details.description && contacts.length === 0 && isOwner && (
                  <p className="text-sm text-muted-foreground">
                    Добавьте описание, отрасль и контакты, их увидят кандидаты в приглашениях.
                  </p>
                )}
              </>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Команда · {details.members.length}</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col divide-y">
              {details.members.map((member) => (
                <li key={member.user_id} className="flex items-center justify-between gap-4 py-2">
                  <span className="truncate">{member.email}</span>
                  <Badge variant={member.role === 'owner' ? 'default' : 'secondary'}>
                    {COMPANY_ROLE_LABELS[member.role]}
                  </Badge>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>
      <div className="flex flex-col gap-4">
        <TrustCard company={details} />
        {isOwner && <InviteLinkCard />}
        {isOwner && <AtsTokensCard />}
      </div>
    </div>
  )
}
