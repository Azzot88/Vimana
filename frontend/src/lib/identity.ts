/**
 * T3.12 pt.4 — taking ownership of your identity, client-side.
 *
 * The private key is generated here, in the browser, and never leaves it. The
 * server receives a public key and a signature over a challenge it issued —
 * nothing it could sign with. That is the whole point of the redesign: a key
 * the platform once held cannot be called sovereign afterwards, because
 * "we deleted our copy" is unprovable.
 *
 * The canonical event below must hash **byte-identically** to the server's
 * `core/identity_proof.py`. `JSON.stringify` on an array emits compact JSON
 * with no spaces, which is what Python's `separators=(",", ":")` produces, and
 * both leave non-ASCII unescaped. Any drift here shows up as a 401 that looks
 * like a wrong key.
 */
import { schnorr } from '@noble/curves/secp256k1'
import { sha256 } from '@noble/hashes/sha256'
import { bytesToHex } from '@noble/hashes/utils'

/** NIP-98 HTTP Auth kind, mirrored from the backend. */
export const PROOF_KIND = 27235
export const PURPOSE_ESTABLISH = 'vimana:identity:establish'

export interface Keypair {
  nsecHex: string
  npubHex: string
}

export interface IdentityProof {
  npub_hex: string
  challenge: string
  created_at: number
  sig: string
}

/** Fresh key, generated locally. Nothing about it is transmitted but the npub. */
export function generateKeypair(): Keypair {
  const priv = schnorr.utils.randomPrivateKey()
  return {
    nsecHex: bytesToHex(priv),
    // x-only, 32 bytes — the same shape the backend stores in `nostr_pubkey`.
    npubHex: bytesToHex(schnorr.getPublicKey(priv)),
  }
}

/**
 * The exact bytes both sides hash. Exported so a test can pin it: this string
 * must match Python's `json.dumps(..., separators=(",", ":"),
 * ensure_ascii=False)` byte for byte, and a drift shows up only as a 401 that
 * reads like "wrong key" — the most expensive kind of bug to chase.
 */
export function canonicalProofEvent(
  npubHex: string,
  purpose: string,
  challenge: string,
  createdAt: number,
): string {
  return JSON.stringify([
    0,
    npubHex,
    createdAt,
    PROOF_KIND,
    [
      ['challenge', challenge],
      ['purpose', purpose],
    ],
    purpose,
  ])
}

export function proofEventId(
  npubHex: string,
  purpose: string,
  challenge: string,
  createdAt: number,
): Uint8Array {
  return sha256(
    new TextEncoder().encode(
      canonicalProofEvent(npubHex, purpose, challenge, createdAt),
    ),
  )
}

/** Sign the challenge with a key we hold locally. */
export function signProofWithKey(
  keypair: Keypair,
  challenge: string,
  purpose: string = PURPOSE_ESTABLISH,
): IdentityProof {
  const createdAt = Math.floor(Date.now() / 1000)
  const id = proofEventId(keypair.npubHex, purpose, challenge, createdAt)
  return {
    npub_hex: keypair.npubHex,
    challenge,
    created_at: createdAt,
    sig: bytesToHex(schnorr.sign(id, keypair.nsecHex)),
  }
}

/**
 * Sign the challenge with a NIP-07 extension.
 *
 * The extension returns its own `id`; we do not trust it and never send it —
 * the backend recomputes the id from the fields anyway, so a mismatch would
 * only surface as an invalid signature. We send exactly the fields the backend
 * hashes.
 */
export async function signProofWithNip07(
  challenge: string,
  purpose: string = PURPOSE_ESTABLISH,
): Promise<IdentityProof | null> {
  if (typeof window === 'undefined' || !window.nostr) return null
  const createdAt = Math.floor(Date.now() / 1000)
  const signed = await window.nostr.signEvent({
    kind: PROOF_KIND,
    created_at: createdAt,
    tags: [
      ['challenge', challenge],
      ['purpose', purpose],
    ],
    content: purpose,
  })
  return {
    npub_hex: signed.pubkey,
    challenge,
    created_at: signed.created_at,
    sig: signed.sig,
  }
}

/** Plain-text backup the user is told to keep. Deliberately not a QR or a
 *  fancy format: this has to survive being printed and typed back in. */
export function keyBackupText(keypair: Keypair): string {
  return [
    'Vimana — your private key',
    '',
    `public  (npub): ${keypair.npubHex}`,
    `private (nsec): ${keypair.nsecHex}`,
    '',
    'Anyone holding the private key IS you on Vimana.',
    'We do not have a copy and cannot restore it.',
  ].join('\n')
}
