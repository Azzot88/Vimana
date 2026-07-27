import api from './client'

export interface ArbiterInfo {
  user_id: string
  npub: string
}

export interface RevealMyShareOut {
  role: 'sender' | 'carrier'
  envelope: string
  /** T3.12 pt.2c — whose public key completes the NIP-04 exchange. Null only if
   *  the message author had no key at write time and the envelope names none. */
  sender_pubkey: string | null
}

export interface ArbiterRevealOut {
  revealed: Array<{ message_id: string; arbiter_share_b64: string }>
  audit_event_id: string
}

export const getArbiterInfo = () =>
  api.get<ArbiterInfo>('/api/threshold/arbiter-info')

export const revealMyShare = (messageId: string) =>
  api.post<RevealMyShareOut>(
    `/api/threshold/dealvault/messages/${messageId}/reveal-my-share`,
  )

export const arbiterReveal = (dealId: string) =>
  api.post<ArbiterRevealOut>(`/api/threshold/disputes/${dealId}/arbiter-reveal`)
