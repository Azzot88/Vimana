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
  /** T3.12.05 — `pending` is an offer nobody has answered; the list never
   *  shows declined or withdrawn ones. */
  state: 'pending' | 'accepted'
  invited_at: string
  accepted_at: string | null
}

/** T3.12.05 — what a person offered the role sees of the deal: enough to
 *  recognise the parcel, nothing that belongs to its participants. */
export interface RecipientOffer {
  id: string
  deal_id: string
  state: 'pending' | 'accepted' | 'declined' | 'revoked'
  route: string
  depart_at: string | null
  sender_name: string | null
  cargo_description: string | null
  invited_at: string
}

/** A link, for a recipient not on the platform yet. It binds to whoever signs
 *  in with it, and they still have to accept. */
export const inviteRecipient = (dealId: string) =>
  api.post<InviteOut>(`/api/deals/${dealId}/invite-recipient`)

/** T3.12.05 — offer the role to somebody already on the platform: from
 *  friends or search you have their id, from a pasted key you have the key. A
 *  key nobody holds comes back 404 — the caller offers a link then. */
export const offerRecipient = (
  dealId: string,
  who: { user_id: string } | { npub: string },
) => api.post<Participant>(`/api/deals/${dealId}/recipient-offers`, who)

/** Bind a link to the signed-in person and read the offer. Accepting is a
 *  separate press. */
export const claimInvite = (token: string) =>
  api.post<RecipientOffer>(`/api/deals/join/${token}`)

export const myRecipientOffers = () =>
  api.get<RecipientOffer[]>('/api/me/recipient-offers')

export const acceptRecipientOffer = (offerId: string) =>
  api.post<RecipientOffer>(`/api/recipient-offers/${offerId}/accept`)

/** `refuseFuture` — «отказаться и больше не предлагать мне эту роль»: also
 *  turns the account setting on. */
export const declineRecipientOffer = (offerId: string, refuseFuture = false) =>
  api.post<RecipientOffer>(`/api/recipient-offers/${offerId}/decline`, {
    refuse_future: refuseFuture,
  })

/** T3.12.05 — «Получатель — я»: no offer, nobody is being asked. */
export const setSelfRecipient = (dealId: string) =>
  api.post<{ recipient_id: string }>(`/api/deals/${dealId}/recipient/self`)

/** The sender takes back the open offer and the role, whichever there is. */
export const withdrawRecipient = (dealId: string) =>
  api.post<{ withdrawn: boolean }>(`/api/deals/${dealId}/recipient/withdraw`)

export const listParticipants = (dealId: string) =>
  api.get<Participant[]>(`/api/deals/${dealId}/participants`)

/** T3.3 — server-mediated decrypt for custodial callers (typically recipients). */
export const decryptMessageForMe = (dealId: string, messageId: string) =>
  api.post<{ message_id: string; text: string }>(
    `/api/deals/${dealId}/dealvault/messages/${messageId}/decrypt-for-me`,
  )
