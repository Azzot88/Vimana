import api from './client'

export interface RegisterPayload {
  display_name: string
  // T3.11 — email is the only identifier. `phone` left the auth path entirely;
  // it stays a profile contact field (see `UserUpdate`).
  email: string
  password: string
  can_carry?: boolean
  can_send?: boolean
  active_mode?: 'sender' | 'carrier'
}

export interface LoginPayload {
  /** An email address. Field name kept for wire compatibility. */
  login: string
  password: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
}

export type UserRole = 'user' | 'arbiter' | 'superuser'

export interface User {
  id: string
  display_name: string
  email: string | null
  phone: string | null
  can_carry: boolean
  can_send: boolean
  active_mode: 'sender' | 'carrier'
  role: UserRole
  nostr_pubkey: string | null
  business_activity_level: number | null
  notify_email: boolean
  notify_telegram: boolean
  notify_whatsapp: boolean
  telegram_chat_id: string | null
  whatsapp_number: string | null
  created_at?: string
  // T1.26 — private receiving address (only present on /me responses).
  receiving_country_iso?: string | null
  receiving_city?: string | null
  receiving_city_geoname_id?: number | null
  receiving_street?: string | null
  receiving_postal_code?: string | null
  receiving_note?: string | null
  // T_UX.4 B — presigned R2 URL, minted per /me response. null if not set.
  avatar_url?: string | null
  // T3.11 — only present on /me. False for an account with no email at all,
  // which is NOT gated: nothing was claimed, so nothing is in limbo.
  email_verified?: boolean
}

// T3.13 — sign in / sign up with a Nostr key. No password involved: the server
// issues a one-time challenge and checks the signature against the claimed key.
export interface NostrChallenge {
  challenge: string
  expires_in: number
  purpose_login: string
  purpose_signup: string
}

export interface NostrProof {
  npub_hex: string
  challenge: string
  created_at: number
  sig: string
}

export const nostrChallenge = (pubkeyHex: string) =>
  api.post<NostrChallenge>('/api/auth/nostr/challenge', {
    pubkey_hex: pubkeyHex,
  })

/** 404 `nostr_pubkey_unknown` means "this key has no account" — offer signup,
 *  do not report it as a failed login. */
export const nostrVerify = (proof: NostrProof) =>
  api.post<TokenResponse>('/api/auth/nostr/verify', proof)

export const nostrSignup = (
  proof: NostrProof & { display_name: string; email?: string },
) => api.post<{ user: User; token: TokenResponse }>('/api/auth/nostr/signup', proof)

// T3.11 — email confirmation. `request-code` answers 202 with
// {status: 'sent' | 'already_verified'}, or 429 while the cooldown holds.
export const requestEmailCode = () =>
  api.post<{ status: string }>('/api/auth/email/request-code')

export const verifyEmail = (code: string) =>
  api.post<{ status: string }>('/api/auth/email/verify', { code })


export const uploadAvatar = (file: File) => {
  const fd = new FormData()
  fd.append('file', file)
  return api.post<User>('/api/me/avatar', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export const deleteAvatar = () => api.delete<User>('/api/me/avatar')

export interface UserUpdate {
  display_name?: string
  phone?: string
  notify_email?: boolean
  notify_telegram?: boolean
  notify_whatsapp?: boolean
  active_mode?: 'sender' | 'carrier'
  can_carry?: boolean
  can_send?: boolean
  receiving_country_iso?: string | null
  receiving_city?: string | null
  receiving_city_geoname_id?: number | null
  receiving_street?: string | null
  receiving_postal_code?: string | null
  receiving_note?: string | null
  whatsapp_number?: string
}

export const register = (payload: RegisterPayload) =>
  api.post<TokenResponse>('/api/auth/register', payload)

export const login = (payload: LoginPayload) =>
  api.post<TokenResponse>('/api/auth/login', payload)

export const me = () =>
  api.get<User>('/api/auth/me')

export const logout = () =>
  api.post<void>('/api/auth/logout')

export const updateMe = (payload: UserUpdate) =>
  api.patch<User>('/api/auth/me', payload)

export const getTelegramLink = () =>
  api.get<{ link: string; already_connected: boolean }>('/api/telegram/connect')
