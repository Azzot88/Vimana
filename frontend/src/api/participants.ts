import api from './client'

export interface InviteOut {
  id: string
  deal_id: string
  role: 'recipient'
  invite_token: string
  invite_url: string
  invited_at: string
}

export interface Participant {
  id: string
  deal_id: string
  user_id: string | null
  display_name: string | null
  npub: string | null
  role: 'recipient'
  invited_at: string
  accepted_at: string | null
}

export const inviteRecipient = (dealId: string) =>
  api.post<InviteOut>(`/api/deals/${dealId}/invite-recipient`)

export const joinDeal = (token: string) =>
  api.post<{ deal_id: string; role: string }>(`/api/deals/join/${token}`)

export const revokeParticipant = (dealId: string, userId: string) =>
  api.post<{ revoked: boolean }>(
    `/api/deals/${dealId}/participants/${userId}/revoke`,
  )

export const listParticipants = (dealId: string) =>
  api.get<Participant[]>(`/api/deals/${dealId}/participants`)

/** T3.3 — server-mediated decrypt for custodial callers (typically recipients). */
export const decryptMessageForMe = (dealId: string, messageId: string) =>
  api.post<{ message_id: string; text: string }>(
    `/api/deals/${dealId}/dealvault/messages/${messageId}/decrypt-for-me`,
  )
