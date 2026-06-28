import api from './client'

export interface VaultMessage {
  id: string
  deal_id: string
  sender_id: string
  sender_name: string
  kind: 'text' | 'handoff_photo' | 'receipt_photo' | 'system'
  body: string
  attachment_url: string | null
  sha256: string
  created_at: string
}

export interface CreateMessagePayload {
  kind: 'text' | 'handoff_photo' | 'receipt_photo'
  body: string
}

export const listMessages = (dealId: string) =>
  api.get<VaultMessage[]>(`/api/deals/${dealId}/vault`)

export const createMessage = (dealId: string, payload: CreateMessagePayload) =>
  api.post<VaultMessage>(`/api/deals/${dealId}/vault`, payload)

export const uploadAttachment = (dealId: string, file: File, kind: 'handoff_photo' | 'receipt_photo') => {
  const form = new FormData()
  form.append('file', file)
  form.append('kind', kind)
  return api.post<VaultMessage>(`/api/deals/${dealId}/vault/upload`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}
