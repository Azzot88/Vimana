/**
 * T2.2 pt.1 — light-touch NIP-07 detection.
 *
 * Alby, nos2x and other Nostr browser extensions inject `window.nostr`. We
 * only *detect* the presence here; actual signing via `window.nostr.signEvent()`
 * is deferred to T2.2 pt.2 (requires backend signing to switch from raw
 * `sha256(payload)` to the NIP-01 event format).
 */

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
