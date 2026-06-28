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
  is_carrier: boolean
  connected_at: string
}

export const createInvite = () =>
  api.post<Invite>('/api/invites')

export const acceptInvite = (token: string) =>
  api.post<{ message: string }>(`/api/invites/${token}/accept`)

export const listConnections = () =>
  api.get<Connection[]>('/api/me/connections')
