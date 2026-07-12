import api from './client'

export interface RegisterPayload {
  display_name: string
  email?: string
  phone?: string
  password: string
  can_carry?: boolean
  can_send?: boolean
  active_mode?: 'sender' | 'carrier'
}

export interface LoginPayload {
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
}

export interface UserUpdate {
  display_name?: string
  phone?: string
  notify_email?: boolean
  notify_telegram?: boolean
  notify_whatsapp?: boolean
  active_mode?: 'sender' | 'carrier'
  can_carry?: boolean
  can_send?: boolean
  whatsapp_number?: string
}

export const register = (payload: RegisterPayload) =>
  api.post<TokenResponse>('/api/auth/register', payload)

export const login = (payload: LoginPayload) =>
  api.post<TokenResponse>('/api/auth/login', payload)

export const me = () =>
  api.get<User>('/api/auth/me')

export const updateMe = (payload: UserUpdate) =>
  api.patch<User>('/api/auth/me', payload)

export const getTelegramLink = () =>
  api.get<{ link: string; already_connected: boolean }>('/api/telegram/connect')
