import api from './client'

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

/** T3.32 — event class → channel → wanted. Keys are not enumerated on purpose:
 *  the server decides which classes are shown and which channels are live, and
 *  a union type here would be a second, quietly diverging copy of that list. */
export type NotificationPrefs = Record<string, Record<string, boolean>>

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
  // T_UX.4 B — presigned R2 URL, minted per /me response. null if not set.
  avatar_url?: string | null
  // T3.11 — only present on /me. False for an account with no email at all,
  // which is NOT gated: nothing was claimed, so nothing is in limbo.
  email_verified?: boolean
  // T3.15 — an address asked for but not yet proven. `email` still holds the
  // working one until the code comes back, so both are shown side by side.
  pending_email?: string | null
  // T3.15 — whether a password exists. Never the hash, never a hint: it only
  // decides whether the profile says "set" or "change".
  has_password?: boolean
  // T3.16 — how many recovery codes are still unused. A count, never the codes:
  // the server cannot show them a second time and does not pretend otherwise.
  recovery_codes_remaining?: number
  /** T3.18 — how much of this identity a stranger may see. */
  public_profile?: 'full' | 'minimal' | 'hidden'
  /** T3.19 — the identity key is gone. Access still works (that is what
   *  `declare-lost` preserves), but this account can no longer sign, and the
   *  shell reads this one bit to decide whether it is showing a participant or
   *  a record. */
  key_lost?: boolean
  /** T3.32 — the full matrix as the screen draws it: only classes that
   *  something actually sends, only channels that are live, and every cell
   *  already filled in. The stored column is partial; this is not. */
  notification_prefs?: NotificationPrefs
  /** Classes that render as a fixed row rather than as choices. Sent by the
   *  server so "security cannot be turned off" is stated in one place. */
  notification_locked?: string[]
  /** Which channels this account actually has an address on. All three are
   *  columns either way; this is what makes the unreachable ones read as
   *  unreachable instead of as boxes that quietly do nothing. */
  notification_channels?: Record<string, boolean>
}

// ── T3.16 — recovery codes ───────────────────────────────────────────────────

/** Generating replaces any previous set, so the answer below is the only place
 *  these strings ever exist outside the user's hands. */
export const issueRecoveryCodes = (stepUpToken: string) =>
  api.post<{ codes: string[]; generated_at: string }>(
    '/api/auth/recovery/codes',
    {},
    { headers: { 'X-Step-Up-Token': stepUpToken } },
  )

export interface RecoverySession {
  access_token: string
  token_type: string
  scope: string
  codes_remaining: number
  /** Grants for exactly the operations a locked-out account needs; keyed by
   *  step-up scope. Consuming a code *is* the proof step-up asks for. */
  step_up_tokens: Record<string, string>
}

/** `identifier` is an email or an npub — whichever the account has. The server
 *  answers the same 401 for a wrong code and an unknown account on purpose, so
 *  the UI must not try to tell the user which one it was. */
export const consumeRecoveryCode = (identifier: string, code: string) =>
  api.post<RecoverySession>('/api/auth/recovery/consume', { identifier, code })

/** T_UX.13 — the Telegram switch turned off: forget the chat entirely. */
export const disconnectTelegram = () =>
  api.post<{ connected: boolean }>('/api/telegram/disconnect')

/** T3.28 — one door. 202 whatever the identifier is, so the screen learns
 *  nothing it could leak about who has an account here. */
export const otpRequest = (identifier: string, channel: string, locale: string) =>
  api.post<{ status: string }>('/api/auth/otp/request', {
    identifier,
    channel,
    locale,
  })

export const otpVerify = (identifier: string, code: string, password?: string) =>
  api.post<{ access_token: string; token_type: string }>('/api/auth/otp/verify', {
    identifier,
    code,
    password: password || undefined,
  })

/** T3.26 — which channels can honestly confirm this identifier. */
export const contactChannels = (identifier: string) =>
  api.post<{ channels: string[] }>('/api/auth/contact/channels', { identifier })

/** T_SEC.5 — 202 whatever the identifier is; the answer never says who exists. */
export const forgotPassword = (identifier: string) =>
  api.post<{ status: string }>('/api/auth/password/forgot', { identifier })

export const resetPassword = (token: string, newPassword: string) =>
  api.post<{ status: string; access_token: string }>('/api/auth/password/reset', {
    token,
    new_password: newPassword,
  })

/** T_SEC.5 — which ways in this identifier can actually use. */
export const loginMethods = (identifier: string) =>
  api.post<{ methods: string[]; can_reset: boolean }>('/api/auth/methods', {
    identifier,
  })

/** T3.15 — moving to a new address. Two steps on purpose: the change is only
 *  requested here, and lands when a code sent to the new mailbox comes back
 *  through `verifyEmail`. Until then the old address keeps working. */
export const changeEmail = (email: string, stepUpToken: string) =>
  api.post<{ status: string; pending_email: string }>(
    '/api/auth/email/change',
    { email },
    { headers: { 'X-Step-Up-Token': stepUpToken } },
  )

/** No step-up: abandoning an unproven claim only restores the state the
 *  account was already in. */
export const cancelEmailChange = () =>
  api.delete<{ status: string }>('/api/auth/email/pending')

/** T3.15 — set or replace the password. There is no `current_password` field:
 *  step-up already proved presence, and demanding the old one would shut out
 *  accounts that never had one.
 *
 *  Every other session ends. The replacement token comes back here and MUST be
 *  stored before the next request — the one in hand was retired by the change,
 *  so carrying it further reads as a logout on the very device that just did
 *  the securing. */
export const changePassword = (newPassword: string, stepUpToken: string) =>
  api.put<{ status: string; access_token: string; token_type: string }>(
    '/api/auth/me/password',
    { new_password: newPassword },
    { headers: { 'X-Step-Up-Token': stepUpToken } },
  )

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
  /** T3.25 — E.164 or the request is refused; the backend normalises and
   *  rejects anything unparseable rather than storing it as text. */
  phone?: string
  /** T_UX.9 — the language every letter to this account is written in. Added
   *  to the backend schema then and missed here; the strict production build
   *  caught it the first time something tried to send it. */
  locale?: string
  public_profile?: 'full' | 'minimal' | 'hidden'
  notify_email?: boolean
  notify_telegram?: boolean
  notify_whatsapp?: boolean
  active_mode?: 'sender' | 'carrier'
  can_carry?: boolean
  can_send?: boolean
  whatsapp_number?: string
  /** T3.32 — send only the cell that changed. The backend merges rather than
   *  assigns, so a partial write is the intended shape, not a shortcut. */
  notification_prefs?: NotificationPrefs
}

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
