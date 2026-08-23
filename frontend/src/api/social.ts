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
