import api from './client'
import type { Page } from './pagination'
import { hasNip07Extension, signVaultMessageViaNip07 } from '../lib/nostr'
import { getKeypairStatus } from './keypair'

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
  nostr_sig?: string | null
  nostr_event_id?: string | null
  nostr_created_at?: number | null
  nostr_pubkey?: string | null
  attachments: Attachment[]
  created_at: string
}

export interface MessageListParams {
  after?: string
  limit?: number
}

export const listMessages = (dealId: string, params?: MessageListParams) =>
  api.get<Page<VaultMessage>>(`/api/deals/${dealId}/dealvault`, { params })

/**
 * Create a vault message. If the current user is on self-custody
 * (`key_self_custody=true`) AND a NIP-07 extension is available, we sign the
 * event client-side and attach `nostr_sig` + `nostr_created_at`. Otherwise we
 * send unsigned and let backend server-sign (custodial path).
 */
export const createMessage = async (dealId: string, text: string, isSystem = false) => {
  const body: {
    text: string
    is_system: boolean
    nostr_sig?: string
    nostr_created_at?: number
  } = { text, is_system: isSystem }

  if (hasNip07Extension()) {
    try {
      const { data: status } = await getKeypairStatus()
      if (status.key_self_custody) {
        const signed = await signVaultMessageViaNip07(dealId, text, isSystem)
        body.nostr_sig = signed.nostr_sig
        body.nostr_created_at = signed.nostr_created_at
      }
    } catch {
      // fall through to unsigned; backend will 422 if user is self-custody
    }
  }

  return api.post<VaultMessage>(`/api/deals/${dealId}/dealvault/messages`, body)
}

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
  const { data: page } = await listMessages(dealId, { limit: 100 })
  const fresh = page.items.find((m) => m.id === msg.id)
  return fresh ?? msg
}
