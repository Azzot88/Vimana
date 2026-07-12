import { create } from 'zustand'
import type { User } from '../api/auth'
import { updateMe } from '../api/auth'

interface AuthStore {
  user: User | null
  token: string | null
  setAuth: (user: User, token: string) => void
  logout: () => void
  switchMode: () => Promise<void>
}

export const useAuthStore = create<AuthStore>((set, get) => ({
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
  switchMode: async () => {
    const current = get().user
    if (!current) return
    const next = current.active_mode === 'carrier' ? 'sender' : 'carrier'
    const { data } = await updateMe({ active_mode: next })
    set({ user: data })
  },
}))
