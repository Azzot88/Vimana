import api from './client'
import type { IdentityProof } from '../lib/identity'

export interface KeypairStatus {
  npub: string | null
  /** T3.12 — false means `npub` is a service key the platform holds, not the
   *  user's identity. */
  identity_established: boolean
  key_lost: boolean
  /** T3.21 — which rung of `D-KEY-TIERS` the account sits on:
   *  `platform_only` only we hold the key · `both` the user has an Identity
   *  Vault too · `user_only` our copy is gone and we can no longer sign. */
  key_copies: 'platform_only' | 'both' | 'user_only'
  /** @deprecated mirrors `identity_established`; kept while callers migrate. */
  key_self_custody: boolean
  /** @deprecated */
  has_encrypted_nsec: boolean
}

export interface IdentityChallenge {
  challenge: string
  expires_in: number
  purpose: string
}

export const getKeypairStatus = () =>
  api.get<KeypairStatus>('/api/me/keypair/status')

export const requestIdentityChallenge = () =>
  api.post<IdentityChallenge>('/api/me/identity/challenge')

export const establishIdentity = (proof: IdentityProof) =>
  api.post<KeypairStatus>('/api/me/identity/establish', proof)

/** T3.21 — the key, once, so this browser can seal it into an Identity Vault.
 *  Our copy stays: this is a second copy appearing, not a handover. The
 *  passphrase is never sent — sealing happens locally, and a passphrase the
 *  server has seen could not protect a file the server keeps. */
export const releaseKeyForVault = (stepUpToken: string) =>
  api.post<{ nsec_hex: string; npub_hex: string }>(
    '/api/me/identity/release-key',
    { step_up_token: stepUpToken },
  )

/** T3.22 — rung 3: we stop holding a copy. The key and the npub do not change
 *  and neither do the deals; what ends is the server's ability to sign or
 *  decrypt for this account. Refused with 409 until an Identity Vault has been
 *  downloaded — otherwise this would destroy the only copy in existence. */
export const deletePlatformCopy = (stepUpToken: string) =>
  api.delete<KeypairStatus>('/api/me/identity/platform-copy', {
    headers: { 'X-Step-Up-Token': stepUpToken },
  })

/** T3.15 — confirmation comes from step-up, not a password field: an account
 *  with no password must be able to do this too. */
export const declareKeyLost = (stepUpToken: string) =>
  api.post<KeypairStatus>('/api/me/identity/declare-lost', {
    step_up_token: stepUpToken,
  })

// T3.12 — `export`, `claim` and `import` are gone from the UI. `import` no
// longer exists server-side at all: it accepted a bare npub with no proof of
// possession, which under "the key is the identity" is impersonation. `export`
// and `claim` still answer on the backend but only so the crypto test suite can
// migrate; nothing in the app calls them.
