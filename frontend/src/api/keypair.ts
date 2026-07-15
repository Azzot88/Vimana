import api from './client'

export interface KeypairStatus {
  npub: string | null
  key_self_custody: boolean
  has_encrypted_nsec: boolean
}

export interface KeypairExport {
  nsec_hex: string
  npub_hex: string
}

export const getKeypairStatus = () =>
  api.get<KeypairStatus>('/api/me/keypair/status')

export const exportKeypair = (password: string) =>
  api.post<KeypairExport>('/api/me/keypair/export', { password })

export const claimSelfCustody = () =>
  api.post<KeypairStatus>('/api/me/keypair/claim')

export const importKeypair = (payload: { nsec_hex?: string; npub_hex?: string }) =>
  api.post<KeypairStatus>('/api/me/keypair/import', payload)
