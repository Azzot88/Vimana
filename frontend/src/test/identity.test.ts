import { describe, expect, it } from 'vitest'
import { schnorr } from '@noble/curves/secp256k1'
import { bytesToHex } from '@noble/hashes/utils'
import {
  PROOF_KIND,
  PURPOSE_ESTABLISH,
  canonicalProofEvent,
  generateKeypair,
  proofEventId,
  signProofWithKey,
} from '../lib/identity'

/**
 * T3.12 — cross-language contract for the identity proof.
 *
 * The backend verifies the signature over a canonical NIP-01 event it rebuilds
 * itself. If our serialization differs from Python's by a single byte, the
 * signature is over different data and `establish` answers 401 — which reads
 * like "wrong key" and sends you looking in entirely the wrong place.
 *
 * `EXPECTED` below is duplicated verbatim in
 * `backend/tests/test_identity_proof_contract.py`. Neither side runs the
 * other's code; both are pinned to the same literal, so they cannot drift
 * apart without one of these tests going red.
 */
const PUBKEY = 'a'.repeat(64)
const CHALLENGE = 'cafebabe'
const CREATED_AT = 1700000000

const EXPECTED =
  `[0,"${PUBKEY}",${CREATED_AT},${PROOF_KIND},` +
  `[["challenge","${CHALLENGE}"],["purpose","${PURPOSE_ESTABLISH}"]],` +
  `"${PURPOSE_ESTABLISH}"]`

describe('identity proof serialization', () => {
  it('matches the canonical form the backend rebuilds', () => {
    expect(
      canonicalProofEvent(PUBKEY, PURPOSE_ESTABLISH, CHALLENGE, CREATED_AT),
    ).toBe(EXPECTED)
  })

  it('emits no whitespace — Python uses separators=(",", ":")', () => {
    const serialized = canonicalProofEvent(
      PUBKEY,
      PURPOSE_ESTABLISH,
      CHALLENGE,
      CREATED_AT,
    )
    expect(serialized).not.toMatch(/[ \n\t]/)
  })

  it('produces a 32-byte id', () => {
    const id = proofEventId(PUBKEY, PURPOSE_ESTABLISH, CHALLENGE, CREATED_AT)
    expect(id).toHaveLength(32)
  })
})

describe('identity keys', () => {
  it('generates an x-only 32-byte public key', () => {
    const { nsecHex, npubHex } = generateKeypair()
    expect(nsecHex).toMatch(/^[0-9a-f]{64}$/)
    expect(npubHex).toMatch(/^[0-9a-f]{64}$/)
  })

  it('generates a different key every time', () => {
    expect(generateKeypair().npubHex).not.toBe(generateKeypair().npubHex)
  })

  it('signs a proof that verifies against the claimed public key', () => {
    const keypair = generateKeypair()
    const proof = signProofWithKey(keypair, CHALLENGE)

    expect(proof.npub_hex).toBe(keypair.npubHex)
    expect(proof.challenge).toBe(CHALLENGE)
    expect(proof.sig).toMatch(/^[0-9a-f]{128}$/)

    const id = proofEventId(
      proof.npub_hex,
      PURPOSE_ESTABLISH,
      proof.challenge,
      proof.created_at,
    )
    expect(schnorr.verify(proof.sig, id, proof.npub_hex)).toBe(true)
  })

  it('does not verify against a different key', () => {
    const keypair = generateKeypair()
    const proof = signProofWithKey(keypair, CHALLENGE)
    const id = proofEventId(
      proof.npub_hex,
      PURPOSE_ESTABLISH,
      proof.challenge,
      proof.created_at,
    )
    expect(schnorr.verify(proof.sig, id, bytesToHex(schnorr.getPublicKey(generateKeypair().nsecHex)))).toBe(
      false,
    )
  })
})
