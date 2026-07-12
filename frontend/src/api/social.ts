import api from './client'

export interface Invite {
  id: string
  token: string
  created_by: string
  used_by: string | null
  created_at: string
}

export interface Connection {
  id: string
  display_name: string
  // Legacy field left for UI display; backend now returns `connected_user.active_mode`.
  is_carrier?: boolean
  connected_at: string
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
