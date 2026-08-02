import api from './client'

export type VerificationLevel = 'auto' | 'peer' | 'kyc'
export type TargetRole = 'sender' | 'carrier'
export type RequestStatus =
  | 'pending'
  | 'later_in_person'
  | 'declined'
  | 'declined_polite'
  | 'verified'
  | 'escalated'
export type BadgeSource = 'auto_ocr' | 'peer' | 'arbiter_review' | 'kyc_provider'
export type RespondAction = 'later_in_person' | 'declined' | 'declined_polite' | 'upload'

export interface VerificationRequest {
  id: string
  deal_id: string
  requested_by_id: string
  target_role: TargetRole
  status: RequestStatus
  created_at: string
  resolved_at: string | null
}

export interface VerificationBadge {
  id: string
  subject_id: string
  level: VerificationLevel
  source: BadgeSource
  verified_by_id: string | null
  in_deal_id: string | null
  verified_at: string
  expires_at: string | null
  revoked_at: string | null
}

export interface UserVerificationSummary {
  subject_id: string
  highest_level: VerificationLevel | null
  /** T_TRUST.1 — when the badge behind `highest_level` was issued. Null when
   *  there is no level, or when the badge carrying it has lapsed. The level is
   *  never rendered without it (`D-EVIDENCE-DECAYS`). */
  highest_level_at: string | null
  /** Counts only badges that are neither revoked nor expired. */
  active_counts: Record<VerificationLevel, number>
  badges: VerificationBadge[]
}

export const createRequest = (dealId: string, targetRole: TargetRole) =>
  api.post<VerificationRequest>(`/api/deals/${dealId}/verification`, {
    target_role: targetRole,
  })

export const listDealRequests = (dealId: string) =>
  api.get<VerificationRequest[]>(`/api/deals/${dealId}/verification-requests`)

export const respondToRequest = (
  dealId: string,
  reqId: string,
  action: RespondAction,
) =>
  api.post<VerificationRequest>(
    `/api/deals/${dealId}/verification/${reqId}/respond`,
    { action },
  )

export const submitDocument = (
  dealId: string,
  reqId: string,
  file: File,
  docType: string,
  docCountry: string,
) => {
  const form = new FormData()
  form.append('file', file)
  form.append('doc_type', docType)
  form.append('doc_country', docCountry)
  return api.post<VerificationBadge>(
    `/api/deals/${dealId}/verification/${reqId}/submit-document`,
    form,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  )
}

export const escalate = (dealId: string, reqId: string, reason: string) =>
  api.post<VerificationRequest>(
    `/api/deals/${dealId}/verification/${reqId}/escalate`,
    { reason },
  )

export const selfUpload = (file: File, docType: string, docCountry: string) => {
  const form = new FormData()
  form.append('file', file)
  form.append('doc_type', docType)
  form.append('doc_country', docCountry)
  return api.post<VerificationBadge>(
    '/api/me/verification/self-upload',
    form,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  )
}

export const getUserVerifications = (userId: string) =>
  api.get<UserVerificationSummary>(`/api/users/${userId}/verifications`)

export const revokeBadge = (badgeId: string) =>
  api.post<VerificationBadge>(`/api/verifications/${badgeId}/revoke`)
