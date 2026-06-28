import { create } from 'zustand'

interface User {
  id: string
  display_name: string
  email: string | null
  phone: string | null
  is_carrier: boolean
  nostr_pubkey: string | null
  business_activity_level: number | null
}

interface AuthStore {
  user: User | null
  token: string | null
  setAuth: (user: User, token: string) => void
  logout: () => void
}

export const useAuthStore = create<AuthStore>((set) => ({
  user: null,
  token: localStorage.getItem('token'),
  setAuth: (user, token) => {
    localStorage.setItem('token', token)
    set({ user, token })
  },
  logout: () => {
    localStorage.removeItem('token')
    set({ user: null, token: null })
  },
}))
