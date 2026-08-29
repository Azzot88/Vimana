import api from './client'

/** T3.42 — one event in the life of one role for one account. Append-only. */
export interface RoleGrant {
  id: string
  /** The one role this event is about — not the account's set of them. */
  role: string
  event: 'offered' | 'accepted' | 'declined' | 'revoked'
  actor_id: string | null
  /** Who proposed it, by name. An id answers "who" only for the database. */
  actor_name: string | null
  reason: string
  created_at: string
}

export interface MyRoles {
  /** Every role this account actually holds. Empty for an ordinary member. */
  roles: string[]
  /** Proposed and unanswered. An entry here grants **nothing**. */
  offers: RoleGrant[]
}

export const myRoles = () => api.get<MyRoles>('/api/me/roles')

export const acceptRole = (role: string) =>
  api.post<RoleGrant>(`/api/me/roles/${role}/accept`)

export const declineRole = (role: string) =>
  api.post<RoleGrant>(`/api/me/roles/${role}/decline`)
