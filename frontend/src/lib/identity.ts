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
import { xchacha20poly1305 } from '@noble/ciphers/chacha'
import { schnorr } from '@noble/curves/secp256k1'
import { scrypt } from '@noble/hashes/scrypt'
import { sha256 } from '@noble/hashes/sha256'
import { bytesToHex, hexToBytes, randomBytes } from '@noble/hashes/utils'
import { bech32 } from '@scure/base'

/** NIP-98 HTTP Auth kind, mirrored from the backend. */
export const PROOF_KIND = 27235
export const PURPOSE_ESTABLISH = 'vimana:identity:establish'
/** T3.13 — distinct purposes so a signature collected for one flow is useless
 *  in another. The purpose is part of the signed payload, not a query flag. */
export const PURPOSE_LOGIN = 'vimana:identity:login'
export const PURPOSE_SIGNUP = 'vimana:identity:signup'

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

// ─────────────────────────────────────────────────────────────
// T3.21 — Identity Vault: sealing the key so it can leave with its owner
// ─────────────────────────────────────────────────────────────

/**
 * NIP-49 (`ncryptsec1…`) — the private key under a passphrase, in the format
 * other Nostr clients already read. Sealing happens **here**, in the browser:
 * a passphrase the server has seen cannot protect a file the server stores,
 * and that difference is the whole of rung 2 in `D-KEY-TIERS`.
 *
 * The container is deliberately not a Vimana invention. A user who never opens
 * our reader can paste the `ncryptsec` string into damus or amethyst and carry
 * on — portability that depends on our software is not portability.
 */
const NIP49_VERSION = 0x02
/** scrypt work factor: N = 2^16. The NIP's own suggested default — heavy enough
 *  to matter on a stolen file, light enough to run in a browser tab. */
const NIP49_LOG_N = 16
/**
 * NIP-49 "key security byte". `0x00` = the key is known to have been handled
 * insecurely at some point.
 *
 * That is the honest value for us and it costs nothing to admit: this key was
 * generated by the platform at registration and its private half lived on our
 * servers. A key established in the browser (`generateKeypair` above) would
 * deserve `0x01`, and when that path produces a file it should say so.
 */
const NIP49_HANDLED_BY_PLATFORM = 0x00

/** What the file looks like on disk. Everything that identifies the owner is
 *  inside `sealed`; the fields left in the clear are only what a reader needs
 *  to know *how* to open it. */
export interface IdentityVaultFile {
  v: 2
  type: 'identity'
  kdf: { n: number; r: number; p: number; salt: string }
  nonce: string
  sealed: string
}

/** What comes out of it. `ncryptsec` travels along so the key can be pasted
 *  into another Nostr client without a second scrypt run. */
export interface IdentityVaultContents {
  npub: string
  nsec: string
  ncryptsec: string
  created_at: string
  label?: string
}

const b64 = (bytes: Uint8Array): string => btoa(String.fromCharCode(...bytes))
const unb64 = (value: string): Uint8Array =>
  Uint8Array.from(atob(value), (c) => c.charCodeAt(0))

export function sealNsec(
  nsecHex: string,
  passphrase: string,
  keySecurity: number = NIP49_HANDLED_BY_PLATFORM,
): string {
  const salt = randomBytes(16)
  const nonce = randomBytes(24)
  // NFKC per the NIP: the same passphrase typed on another keyboard layout or
  // pasted from another app must derive the same key.
  const key = scrypt(passphrase.normalize('NFKC'), salt, {
    N: 2 ** NIP49_LOG_N,
    r: 8,
    p: 1,
    dkLen: 32,
  })
  const ad = new Uint8Array([keySecurity])
  const ciphertext = xchacha20poly1305(key, nonce, ad).encrypt(hexToBytes(nsecHex))

  const payload = new Uint8Array(1 + 1 + 16 + 24 + 1 + ciphertext.length)
  payload[0] = NIP49_VERSION
  payload[1] = NIP49_LOG_N
  payload.set(salt, 2)
  payload.set(nonce, 18)
  payload[42] = keySecurity
  payload.set(ciphertext, 43)

  // The default bech32 limit is 90 characters — this string is far longer, and
  // the encoder silently refuses rather than truncating. The NIP has no length
  // cap, so the limit is raised instead of the payload trimmed.
  return bech32.encode('ncryptsec', bech32.toWords(payload), 500)
}

/** Inverse of `sealNsec`. Throws if the passphrase is wrong — there is nothing
 *  to check it against but the ciphertext itself, which is the point. */
export function openNsec(ncryptsec: string, passphrase: string): string {
  const { prefix, words } = bech32.decode(ncryptsec as `${string}1${string}`, 500)
  if (prefix !== 'ncryptsec') throw new Error('Not an ncryptsec string')
  const payload = bech32.fromWords(words)
  const logN = payload[1]
  const salt = Uint8Array.from(payload.slice(2, 18))
  const nonce = Uint8Array.from(payload.slice(18, 42))
  const keySecurity = payload[42]
  const ciphertext = Uint8Array.from(payload.slice(43))

  const key = scrypt(passphrase.normalize('NFKC'), salt, {
    N: 2 ** logN,
    r: 8,
    p: 1,
    dkLen: 32,
  })
  const plain = xchacha20poly1305(key, nonce, new Uint8Array([keySecurity])).decrypt(
    ciphertext,
  )
  return bytesToHex(plain)
}

/** NIP-19 `npub1…`. Hex stays the internal representation; bech32 is what the
 *  rest of the Nostr world reads, and what belongs in a portable file. */
export function npubBech32(pubkeyHex: string): string {
  return bech32.encode('npub', bech32.toWords(hexToBytes(pubkeyHex)), 200)
}

/**
 * The `.dvlt` payload — same extension and shape family as a deal export
 * (`D-DVLT-PROTOCOL`), distinguished by `type`. One reader opens both.
 *
 * **Format 2 seals the whole container, not just the key.** In v1 the `npub`
 * and the timestamp sat in the clear: the key was safe, but the file announced
 * whose it was to anyone who opened it in a text editor. A backup that names
 * its owner is a different object from one that does not — it turns "a file on
 * a flash drive" into "this person's identity, on a flash drive".
 *
 * What stays readable is only what a reader needs to know how to proceed:
 * the format version, the type, and the KDF parameters. Reading anything else
 * costs the passphrase.
 */
export function buildIdentityVault(
  npubHex: string,
  nsecHex: string,
  passphrase: string,
  label?: string,
): IdentityVaultFile {
  const salt = randomBytes(16)
  const nonce = randomBytes(24)
  const key = scrypt(passphrase.normalize('NFKC'), salt, {
    N: 2 ** NIP49_LOG_N,
    r: 8,
    p: 1,
    dkLen: 32,
  })
  const contents: IdentityVaultContents = {
    npub: npubBech32(npubHex),
    nsec: nsecHex,
    // Carried inside so another Nostr client can be fed a standard string
    // without a second scrypt pass at open time.
    ncryptsec: sealNsec(nsecHex, passphrase),
    created_at: new Date().toISOString(),
    ...(label ? { label } : {}),
  }
  const sealed = xchacha20poly1305(key, nonce).encrypt(
    new TextEncoder().encode(JSON.stringify(contents)),
  )
  return {
    v: 2,
    type: 'identity',
    kdf: { n: 2 ** NIP49_LOG_N, r: 8, p: 1, salt: b64(salt) },
    nonce: b64(nonce),
    sealed: b64(sealed),
  }
}

/** Inverse of `buildIdentityVault`. Throws on a wrong passphrase — the tag
 *  fails, so there is no half-open state to misread. */
export function openIdentityVault(
  file: IdentityVaultFile,
  passphrase: string,
): IdentityVaultContents {
  const key = scrypt(passphrase.normalize('NFKC'), unb64(file.kdf.salt), {
    N: file.kdf.n,
    r: file.kdf.r,
    p: file.kdf.p,
    dkLen: 32,
  })
  const plain = xchacha20poly1305(key, unb64(file.nonce)).decrypt(unb64(file.sealed))
  return JSON.parse(new TextDecoder().decode(plain)) as IdentityVaultContents
}

/** Accepts what a person actually has in hand: a `nsec1…` string from any
 *  Nostr client, or the raw hex our own backup file printed. Returns hex —
 *  the internal representation everywhere else in this module. */
export function parseNsecInput(raw: string): string {
  const value = (raw || '').trim()
  if (/^[0-9a-fA-F]{64}$/.test(value)) return value.toLowerCase()
  if (value.startsWith('nsec1')) {
    const { prefix, words } = bech32.decode(value as `${string}1${string}`, 200)
    if (prefix !== 'nsec') throw new Error('Not an nsec string')
    return bytesToHex(Uint8Array.from(bech32.fromWords(words)))
  }
  throw new Error('Unrecognised key format')
}

/** The npub that belongs to a private key — so a file sealed from a pasted key
 *  carries the right public half, rather than trusting whatever was typed
 *  alongside it. */
export function npubFromNsec(nsecHex: string): string {
  return bytesToHex(schnorr.getPublicKey(hexToBytes(nsecHex)))
}
