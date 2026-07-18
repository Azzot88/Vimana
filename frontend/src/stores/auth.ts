import { create } from 'zustand'
import type { User } from '../api/auth'
import { me, updateMe } from '../api/auth'

export type AuthState = 'loading' | 'authenticated' | 'anonymous'

interface AuthStore {
  user: User | null
  token: string | null
  authState: AuthState
  /** Last activity timestamp (ms since epoch). Updated by AuthBootstrap. */
  lastActivityAt: number
  setAuth: (user: User, token: string) => void
  logout: (reason?: 'inactivity' | 'manual') => void
  switchMode: () => Promise<void>
  /** T_UX.3 pt.1 — call once on app boot. Reads localStorage token, hits
   *  /api/auth/me to populate user. On 401 → clean logout. */
  hydrate: () => Promise<void>
  bumpActivity: () => void
}

export const useAuthStore = create<AuthStore>((set, get) => ({
  user: null,
  token: localStorage.getItem('token'),
  authState: 'loading',
  lastActivityAt: Date.now(),
  setAuth: (user, token) => {
    localStorage.setItem('token', token)
    set({ user, token, authState: 'authenticated', lastActivityAt: Date.now() })
  },
  logout: (reason) => {
    localStorage.removeItem('token')
    set({ user: null, token: null, authState: 'anonymous' })
    if (reason === 'inactivity' && typeof window !== 'undefined') {
      // Full page nav so any stale state elsewhere is wiped.
      window.location.replace('/login?reason=inactivity')
    }
  },
  switchMode: async () => {
    const current = get().user
    if (!current) return
    const next = current.active_mode === 'carrier' ? 'sender' : 'carrier'
    const { data } = await updateMe({ active_mode: next })
    set({ user: data })
  },
  hydrate: async () => {
    const token = get().token
    if (!token) {
      set({ authState: 'anonymous' })
      return
    }
    try {
      const { data } = await me()
      set({ user: data, authState: 'authenticated', lastActivityAt: Date.now() })
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status
      if (status === 401 || status === 403) {
        localStorage.removeItem('token')
        set({ user: null, token: null, authState: 'anonymous' })
      } else {
        // Network / server error — keep token, mark unauthenticated for now,
        // ProtectedRoute will redirect to /login; user re-signs when back online.
        set({ authState: 'anonymous' })
      }
    }
  },
  bumpActivity: () => {
    set({ lastActivityAt: Date.now() })
  },
}))
