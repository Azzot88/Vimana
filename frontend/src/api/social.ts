import api from './client'

export interface Invite {
  id: string
  token: string
  created_by: string
  used_by: string | null
  created_at: string
}

/** The counterparty as `UserOut` describes them — a subset, and only fields the
 *  contact list actually reads. */
export interface ConnectedUser {
  id: string
  display_name: string
  active_mode: string
  can_carry: boolean
  can_send: boolean
}

/**
 * Shaped after `schemas/social.ConnectionOut`, which is not what this said
 * before.
 *
 * It declared `display_name`, `is_carrier` and `connected_at` — flat fields the
 * endpoint has never returned in this form. Of the four, only `id` was real.
 * The contact list read `conn.display_name[0]`, got `undefined[0]`, and took
 * the whole profile screen down with it for **any account with at least one
 * contact**. It stayed invisible because an account with no contacts renders
 * the empty state and never reaches the row.
 *
 * A hand-written interface is an assertion about somebody else's code, and
 * TypeScript checks it against nothing. The comment that used to sit on
 * `is_carrier` — "backend now returns `connected_user.active_mode`" — shows the
 * drift was even noticed once, on one field, and the type was left describing
 * the old shape anyway.
 */
export interface Connection {
  /** T3.12.06 — see `ConnectionState` below. */
  state?: ConnectionState
  id: string
  connected_user_id: string
  connected_user: ConnectedUser
  created_at: string
}

export interface MyInvite {
  token: string
  created_at: string
  expires_at: string
  status: 'pending' | 'accepted' | 'expired'
  accepted_by_display_name: string | null
}

export const createInvite = () =>
  api.post<Invite>('/api/invites')

export const acceptInvite = (token: string) =>
  api.post<{ message: string }>(`/api/invites/${token}/accept`)

export const listMyInvites = () =>
  api.get<MyInvite[]>('/api/invites/mine')

export const listConnections = () =>
  api.get<Connection[]>('/api/me/connections')

/** T3.12.06 — what is true between two people: a contact, a request one way or
 *  the other, or close. Closeness is asked and accepted, never declared. */
export type ConnectionState = 'connection' | 'close_pending' | 'close_requested' | 'close'

export const addConnection = (userId: string) =>
  api.post<Connection>('/api/me/connections', { user_id: userId })

export const removeConnection = (userId: string) =>
  api.delete<void>(`/api/me/connections/${userId}`)

/** T3.12.06 — one close person, or one request, from my side. */
export interface ClosePair {
  id: string
  user_id: string
  display_name: string | null
  handle: string | null
  state: 'close' | 'close_pending' | 'close_requested' | 'none'
  requested_at: string
  accepted_at: string | null
}

export const listClose = () => api.get<ClosePair[]>('/api/me/close')

/** Ask a contact to be close. Asking somebody who asked me is accepting. */
export const requestClose = (userId: string) =>
  api.post<ClosePair>('/api/me/close', { user_id: userId })

export const acceptClose = (pairId: string) =>
  api.post<ClosePair>(`/api/me/close/${pairId}/accept`)

export const declineClose = (pairId: string) =>
  api.post<ClosePair>(`/api/me/close/${pairId}/decline`)

/** End it from my side: no longer close, withdraw my request, or turn down theirs. */
export const endClose = (userId: string) => api.delete<void>(`/api/me/close/${userId}`)

/** Search matches the display name and the public key — the two things a person
 *  has to hand when looking somebody up. */
export const searchConnections = (q: string) =>
  api.get<Connection[]>('/api/me/connections', { params: { q } })

/** T3.11.24 — one person, by something you already know about them: their
 *  handle, the email or the phone in their cabinet. **Exact match**, on the
 *  server's insistence: a prefix search over addresses is a harvester. */
export interface FoundUser {
  id: string
  display_name: string
  handle: string | null
}

export const lookupUser = (q: string) =>
  api.get<FoundUser[]>('/api/users/lookup', { params: { q } })
