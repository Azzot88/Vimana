import api from './client'
import type { Page } from './pagination'
import { hasNip07Extension, signVaultMessageViaNip07 } from '../lib/nostr'
import { encryptE2E, type E2EPayload } from '../lib/threshold'
import { getKeypairStatus } from './keypair'
import { getArbiterInfo } from './threshold'

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
  is_e2e?: boolean
  ciphertext_b64?: string | null
  nonce_b64?: string | null
  read_packages?: { sender?: string; carrier?: string } | null
  attachments: Attachment[]
  created_at: string
}

export interface E2EParties {
  senderNpub: string
  carrierNpub: string
}

export interface MessageListParams {
  after?: string
  limit?: number
}

export const listMessages = (dealId: string, params?: MessageListParams) =>
  api.get<Page<VaultMessage>>(`/api/deals/${dealId}/dealvault`, { params })

/**
 * Create a vault message.
 *
 * Behaviour matrix:
 * - self-custody + NIP-07 + all party npubs known → **e2e path**: encrypt
 *   client-side (T2.3), sign NIP-07 (T2.2 pt.2), send `e2e_payload`.
 * - self-custody + NIP-07 without party info → server-signed but plaintext.
 * - custodial → server-signed plaintext (T1.21 legacy at-rest encryption).
 */
export const createMessage = async (
  dealId: string,
  text: string,
  isSystem = false,
  parties?: E2EParties,
) => {
  const body: {
    text?: string
    is_system: boolean
    nostr_sig?: string
    nostr_created_at?: number
    e2e_payload?: E2EPayload
  } = { is_system: isSystem }

  let goE2E = false
  if (hasNip07Extension() && parties) {
    try {
      const { data: status } = await getKeypairStatus()
      if (status.key_self_custody) {
        const { data: arbiter } = await getArbiterInfo()
        body.e2e_payload = await encryptE2E(
          text,
          parties.senderNpub,
          parties.carrierNpub,
          arbiter.npub,
        )
        // Sign the (empty-content) event skeleton so audit trail still records
        // authorship — content bound to sig here is the encrypted ciphertext.
        const signed = await signVaultMessageViaNip07(dealId, '', isSystem)
        body.nostr_sig = signed.nostr_sig
        body.nostr_created_at = signed.nostr_created_at
        goE2E = true
      }
    } catch {
      // fall through to plaintext path
    }
  }

  if (!goE2E) {
    body.text = text
    if (hasNip07Extension()) {
      try {
        const { data: status } = await getKeypairStatus()
        if (status.key_self_custody) {
          const signed = await signVaultMessageViaNip07(dealId, text, isSystem)
          body.nostr_sig = signed.nostr_sig
          body.nostr_created_at = signed.nostr_created_at
        }
      } catch {
        // let backend 422 if self-custody
      }
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
