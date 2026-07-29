import api from './client'
import type { TokenResponse, User } from './auth'

/**
 * T3.14 — passkeys.
 *
 * Every ceremony is two calls: `options` mints a challenge and returns a
 * `ceremony_id`, then `verify` sends the authenticator's answer back with that
 * id. The id is the only thing tying the two halves together — the server keys
 * its state on it rather than on the user, because login has no user to key on
 * and two open tabs would otherwise clobber each other's ceremony.
 */
export interface PasskeyOptions {
  ceremony_id: string
  /** Raw WebAuthn options — handed to the browser untouched; the shape is the
   *  spec's, not ours. */
  options: Record<string, unknown>
  expires_in: number
}

export type DeviceKind = 'hardware_key' | 'synced_passkey' | 'device_passkey'

export interface PasskeyCredential {
  id: string
  device_name: string | null
  device_kind: DeviceKind
  created_at: string
  last_used_at: string | null
}

export const passkeyRegisterOptions = () =>
  api.post<PasskeyOptions>('/api/auth/passkey/register/options')

export const passkeyRegisterVerify = (payload: {
  ceremony_id: string
  credential: unknown
  device_name?: string
}) => api.post<PasskeyCredential>('/api/auth/passkey/register/verify', payload)

export const passkeyLoginOptions = () =>
  api.post<PasskeyOptions>('/api/auth/passkey/login/options')

export const passkeyLoginVerify = (payload: {
  ceremony_id: string
  credential: unknown
}) => api.post<TokenResponse>('/api/auth/passkey/login/verify', payload)

export const passkeySignupOptions = (payload: {
  display_name: string
  email?: string
}) => api.post<PasskeyOptions>('/api/auth/passkey/signup/options', payload)

export const passkeySignupVerify = (payload: {
  ceremony_id: string
  credential: unknown
  device_name?: string
}) =>
  api.post<{ user: User; token: TokenResponse }>(
    '/api/auth/passkey/signup/verify',
    payload,
  )

/** Trailing slash on purpose: it matches the nginx `location
 *  /api/auth/passkey/` block, so this request gets the same rate-limit zone as
 *  the rest of the flow instead of falling through to the generic `/api/` one. */
export const listPasskeys = () =>
  api.get<PasskeyCredential[]>('/api/auth/passkey/')

export const deletePasskey = (id: string) =>
  api.delete(`/api/auth/passkey/${id}`)
