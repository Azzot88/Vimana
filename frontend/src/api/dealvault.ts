import api from './client'
import type { Page } from './pagination'

export type AttachmentKind = 'handoff_photo' | 'receipt_photo' | 'doc' | 'payment_receipt'

export interface Attachment {
  id: string
  message_id: string
  r2_key: string
  file_hash: string
  ipfs_cid: string | null
  kind: AttachmentKind
  url: string | null
  created_at: string
}

export interface VaultMessage {
  id: string
  deal_id: string
  sender_id: string | null
  text: string | null
  is_system: boolean
  attachments: Attachment[]
  created_at: string
}

export interface MessageListParams {
  after?: string
  limit?: number
}

export const listMessages = (dealId: string, params?: MessageListParams) =>
  api.get<Page<VaultMessage>>(`/api/deals/${dealId}/dealvault`, { params })

export const createMessage = (dealId: string, text: string, isSystem = false) =>
  api.post<VaultMessage>(`/api/deals/${dealId}/dealvault/messages`, {
    text,
    is_system: isSystem,
  })

export const shareAddressInVault = (dealId: string) =>
  api.post<VaultMessage>(`/api/deals/${dealId}/dealvault/messages/share-address`)

export const uploadAttachment = (
  dealId: string,
  messageId: string,
  file: File,
  kind: AttachmentKind,
) => {
  const form = new FormData()
  form.append('file', file)
  form.append('kind', kind)
  return api.post<Attachment>(
    `/api/deals/${dealId}/dealvault/messages/${messageId}/attachments`,
    form,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  )
}

/**
 * High-level helper: creates a placeholder message and attaches the file.
 * Returns the reloaded message (with attachment) for the UI to insert.
 */
export const sendPhotoMessage = async (
  dealId: string,
  file: File,
  kind: AttachmentKind,
): Promise<VaultMessage> => {
  const { data: msg } = await createMessage(dealId, '', false)
  await uploadAttachment(dealId, msg.id, file, kind)
  // Re-fetch a single-page window that contains this message id.
  const { data: page } = await listMessages(dealId, { limit: 100 })
  const fresh = page.items.find((m) => m.id === msg.id)
  return fresh ?? msg
}
