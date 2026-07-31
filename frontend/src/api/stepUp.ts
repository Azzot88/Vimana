import api from './client'

/**
 * T3.15 — step-up: a fresh confirmation before an irreversible action.
 *
 * Two calls. `options` says which proofs this account can actually produce —
 * so the UI never asks for a password from an account that has none — and
 * hands out a challenge for the signature-based ones. `verify` takes exactly
 * one proof and returns a token good for one operation, once, for five minutes.
 */
export type StepUpScope =
  | 'declare_lost'
  | 'unlink_passkey'
  | 'change_email'
  /** Covers setting a first password as well as replacing one — one operation
   *  from the user's side, one confirmation. */
  | 'change_password'
  | 'add_auth_method'

export type StepUpMethod = 'password' | 'passkey' | 'nostr'

export interface StepUpOptions {
  methods: StepUpMethod[]
  scope: StepUpScope
  /** Exact string that must sit inside a signed Nostr event — it carries the
   *  scope, so a signature cannot be moved to another operation. */
  purpose: string
  challenge: string | null
  webauthn: Record<string, unknown> | null
  expires_in: number
}

export interface StepUpGrant {
  step_up_token: string
  scope: StepUpScope
  expires_in: number
}

export const stepUpOptions = (scope: StepUpScope) =>
  api.post<StepUpOptions>('/api/auth/step-up/options', { scope })

export const stepUpVerify = (payload: {
  scope: StepUpScope
  password?: string
  nostr?: Record<string, unknown>
  webauthn?: Record<string, unknown>
}) => api.post<StepUpGrant>('/api/auth/step-up/verify', payload)
