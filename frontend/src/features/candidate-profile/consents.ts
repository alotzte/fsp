import { useQueryClient } from '@tanstack/react-query'

import {
  getGetMyCandidateProfileQueryKey,
  getGetMyEmployerViewQueryKey,
  useGrantConsent,
  useRevokeConsent,
} from '@/api/generated/candidate/candidate'
import type { ConsentKind, ConsentStateRead } from '@/api/generated/model'

export function isConsentActive(consents: ConsentStateRead[], kind: ConsentKind): boolean {
  return consents.some((consent) => consent.kind === kind && consent.is_active)
}

/** Мутации согласий. После любой из них профиль перечитывается: меняются is_published и exists. */
export function useConsentMutations() {
  const queryClient = useQueryClient()
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: getGetMyCandidateProfileQueryKey() })
    void queryClient.invalidateQueries({ queryKey: getGetMyEmployerViewQueryKey() })
  }
  const grant = useGrantConsent({ mutation: { onSuccess: refresh } })
  const revoke = useRevokeConsent({ mutation: { onSuccess: refresh } })
  return { grant, revoke }
}
