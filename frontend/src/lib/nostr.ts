/**
 * T2.2 pt.2 — NIP-01 event build + NIP-07 signing helpers.
 *
 * Detection (pt.1): `hasNip07Extension()`, `getNip07Pubkey()`.
 * Signing (pt.2): build vault-message events matching backend `signing.py`
 * shape and pass them to `window.nostr.signEvent()`.
 */

export const NOSTR_KIND_VAULT_MESSAGE = 4801

interface NostrExtension {
  getPublicKey(): Promise<string>
  signEvent(event: {
    kind: number
    created_at: number
    tags: string[][]
    content: string
  }): Promise<{
    id: string
    sig: string
    pubkey: string
    kind: number
    created_at: number
    tags: string[][]
    content: string
  }>
}

declare global {
  interface Window {
    nostr?: NostrExtension
  }
}

export function hasNip07Extension(): boolean {
  return typeof window !== 'undefined' && typeof window.nostr === 'object'
}

export async function getNip07Pubkey(): Promise<string | null> {
  if (!hasNip07Extension() || !window.nostr) return null
  try {
    return await window.nostr.getPublicKey()
  } catch {
    return null
  }
}

export interface SignedVaultMessage {
  nostr_sig: string
  nostr_created_at: number
}

/**
 * Build a NIP-01 vault-message event and sign via NIP-07.
 *
 * Tags must match `_tags_vault_message` in `backend/app/core/signing.py`.
 * If they diverge, backend event_id recompute won't match sig → 422.
 */
export async function signVaultMessageViaNip07(
  dealId: string,
  text: string,
  isSystem: boolean,
): Promise<SignedVaultMessage> {
  if (!hasNip07Extension() || !window.nostr) {
    throw new Error('NIP-07 extension not available')
  }
  const tags: string[][] = [
    ['k', 'vault_message'],
    ['deal', dealId],
  ]
  if (isSystem) tags.push(['system', '1'])
  const created_at = Math.floor(Date.now() / 1000)
  const signed = await window.nostr.signEvent({
    kind: NOSTR_KIND_VAULT_MESSAGE,
    created_at,
    tags,
    content: text,
  })
  return { nostr_sig: signed.sig, nostr_created_at: created_at }
}
