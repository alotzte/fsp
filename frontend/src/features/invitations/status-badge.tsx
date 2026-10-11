import type { InvitationStatus } from '@/api/generated/model'
import { Badge } from '@/components/ui/badge'
import { INVITATION_STATUS_LABELS } from '@/features/invitations/format'

const VARIANTS: Record<InvitationStatus, 'default' | 'secondary' | 'outline' | 'destructive'> = {
  sent: 'outline',
  viewed: 'secondary',
  accepted: 'default',
  declined: 'destructive',
  withdrawn: 'outline',
  expired: 'outline',
}

export function InvitationStatusBadge({ status }: { status: InvitationStatus }) {
  return <Badge variant={VARIANTS[status]}>{INVITATION_STATUS_LABELS[status]}</Badge>
}
