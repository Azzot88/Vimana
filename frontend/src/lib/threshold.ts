/**
 * T2.3 — Threshold 2-of-3 client-side crypto.
 *
 * Flow on write:
 *   session_key <- random(32)
 *   ciphertext  <- AES-256-GCM(session_key, plaintext)
 *   [A, B, C]   <- shamir.split(session_key, 3, 2)
 *   wrapped_shares.sender   = NIP-04(A, writer_priv → sender_pub)
 *   wrapped_shares.carrier  = NIP-04(B, writer_priv → carrier_pub)
 *   wrapped_shares.arbiter  = NIP-04(C, writer_priv → arbiter_pub)
 *   read_packages.sender    = NIP-04(session_key, writer_priv → sender_pub)
 *   read_packages.carrier   = NIP-04(session_key, writer_priv → carrier_pub)
 *
 * Encryption/decryption uses `window.nostr.nip04.*` (self-custody only). We
 * intentionally do NOT expose a custodial fallback — the whole point of T2.3
 * is that the server never touches the session key.
 */
import { gcm } from '@noble/ciphers/aes'
import { secp256k1 } from '@noble/curves/secp256k1'
import { bytesToHex, hexToBytes, randomBytes, utf8ToBytes } from '@noble/hashes/utils'
import { split as sssSplit, combine as sssCombine } from 'shamir-secret-sharing'

export interface E2EPayload {
  ciphertext: string       // base64
  nonce: string            // base64 (12 bytes)
  wrapped_shares: {
    sender: string
    carrier: string
    arbiter: string
  }
  read_packages: {
    sender: string
    carrier: string
  }
}

function b64(bytes: Uint8Array): string {
  let s = ''
  for (const b of bytes) s += String.fromCharCode(b)
  return btoa(s)
}

function fromB64(s: string): Uint8Array {
  const bin = atob(s)
  const out = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i)
  return out
}

/**
 * NIP-07 must be available and the user must be self-custody; otherwise this
 * refuses so we don't silently downgrade to a server-visible mode.
 */
function requireNip07(): NonNullable<Window['nostr']> {
  if (typeof window === 'undefined' || !window.nostr) {
    throw new Error('NIP-07 extension required for e2e vault messages')
  }
  return window.nostr
}

/** Encrypt session-key material as NIP-04 ciphertext addressed to `recipientNpub`.
 * Uses the extension's own privkey — writer identity is implicit in NIP-07. */
async function nip04Encrypt(payload: Uint8Array, recipientNpub: string): Promise<string> {
  const nostr = requireNip07()
  const nip04 = (nostr as unknown as { nip04?: { encrypt(pub: string, text: string): Promise<string> } }).nip04
  if (!nip04) throw new Error('NIP-07 extension does not expose nip04.encrypt')
  return nip04.encrypt(recipientNpub, bytesToHex(payload))
}

async function nip04Decrypt(ct: string, senderNpub: string): Promise<Uint8Array> {
  const nostr = requireNip07()
  const nip04 = (nostr as unknown as { nip04?: { decrypt(pub: string, ct: string): Promise<string> } }).nip04
  if (!nip04) throw new Error('NIP-07 extension does not expose nip04.decrypt')
  const hex = await nip04.decrypt(senderNpub, ct)
  return hexToBytes(hex)
}

/**
 * Build the e2e blob. `writerNpub` is passed only for future audit; encryption
 * side of NIP-07 already uses the extension's own key.
 */
export async function encryptE2E(
  plaintext: string,
  senderNpub: string,
  carrierNpub: string,
  arbiterNpub: string,
): Promise<E2EPayload> {
  const sessionKey = randomBytes(32)
  const nonce = randomBytes(12)
  const ct = gcm(sessionKey, nonce).encrypt(utf8ToBytes(plaintext))

  const shares = await sssSplit(sessionKey, 3, 2)
  // sssSplit returns Uint8Array[] of length 3.
  const [shareA, shareB, shareC] = shares

  const [
    wSender, wCarrier, wArbiter,
    rSender, rCarrier,
  ] = await Promise.all([
    nip04Encrypt(shareA, senderNpub),
    nip04Encrypt(shareB, carrierNpub),
    nip04Encrypt(shareC, arbiterNpub),
    nip04Encrypt(sessionKey, senderNpub),
    nip04Encrypt(sessionKey, carrierNpub),
  ])

  return {
    ciphertext: b64(ct),
    nonce: b64(nonce),
    wrapped_shares: { sender: wSender, carrier: wCarrier, arbiter: wArbiter },
    read_packages: { sender: rSender, carrier: rCarrier },
  }
}

/**
 * Normal-read path: caller has their own read_package. Decrypts under
 * NIP-07 → session_key, then AES-256-GCM-decrypts the ciphertext.
 *
 * `writerNpub` is the message author (whose privkey encrypted the NIP-04
 * envelope) — passed as `sender_pub` to `window.nostr.nip04.decrypt`.
 */
export async function decryptE2E(
  ciphertextB64: string,
  nonceB64: string,
  ownReadPackage: string,
  writerNpub: string,
): Promise<string> {
  const sessionKey = await nip04Decrypt(ownReadPackage, writerNpub)
  const ct = fromB64(ciphertextB64)
  const nonce = fromB64(nonceB64)
  const pt = gcm(sessionKey, nonce).decrypt(ct)
  return new TextDecoder().decode(pt)
}

/**
 * Dispute-time recovery: arbiter's client received their unwrapped share via
 * `/arbiter-reveal`. Combined with a cooperating party's revealed share we
 * reconstruct the session key and decrypt.
 */
export async function decryptFromShares(
  ciphertextB64: string,
  nonceB64: string,
  shareA: Uint8Array,
  shareB: Uint8Array,
): Promise<string> {
  const sessionKey = await sssCombine([shareA, shareB])
  const ct = fromB64(ciphertextB64)
  const nonce = fromB64(nonceB64)
  const pt = gcm(sessionKey, nonce).decrypt(ct)
  return new TextDecoder().decode(pt)
}

// Re-export helpers so downstream modules stay consistent.
export { bytesToHex, hexToBytes, b64, fromB64 }

// Suppress unused-warning for `secp256k1` — we may add local sig verification
// in a future revision without changing the public API. If it stays unused for
// long, drop it and the dep pair.
export const _secp256k1 = secp256k1
