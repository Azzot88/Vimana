import api from './client'

export interface RegisterPayload {
  display_name: string
  email?: string
  phone?: string
  password: string
  is_carrier: boolean
}

export interface LoginPayload {
  login: string
  password: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
}

export interface User {
  id: string
  display_name: string
  email: string | null
  phone: string | null
  is_carrier: boolean
  nostr_pubkey: string | null
  business_activity_level: number | null
}

export const register = (payload: RegisterPayload) =>
  api.post<TokenResponse>('/api/auth/register', payload)

export const login = (payload: LoginPayload) =>
  api.post<TokenResponse>('/api/auth/token', payload)

export const me = () =>
  api.get<User>('/api/me')
