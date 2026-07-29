import api from './client'
import type { IdentityProof } from '../lib/identity'

export interface KeypairStatus {
  npub: string | null
  /** T3.12 — false means `npub` is a service key the platform holds, not the
   *  user's identity. */
  identity_established: boolean
  key_lost: boolean
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
