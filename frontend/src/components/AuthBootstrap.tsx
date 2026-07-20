import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../stores/auth'

/**
 * T_UX.3 — one component that owns:
 *   pt.1: rehydrate auth from localStorage on app boot (before rendering
 *         routes so ProtectedRoute never sees a transient `token && !user`
 *         state).
 *   pt.2: inactivity timer — 30 min default, warning modal 2 min before,
 *         auto-logout with `?reason=inactivity` banner on LoginPage.
 *
 * Option-A logout (frontend-only): clears localStorage token; backend JWT
 * remains valid until its natural expiry. Option-B (backend blacklist) —
 * deferred to pt.4 follow-up.
 */

const INACTIVITY_MS = Number(
  (import.meta as unknown as { env?: { VITE_INACTIVITY_MS?: string } }).env
    ?.VITE_INACTIVITY_MS ?? 30 * 60 * 1000,
)
const WARN_BEFORE_MS = 2 * 60 * 1000
const CHECK_INTERVAL_MS = 30 * 1000
const ACTIVITY_DEBOUNCE_MS = 10 * 1000

interface Props {
  children: ReactNode
}

export default function AuthBootstrap({ children }: Props) {
  const { t } = useTranslation()
  const authState = useAuthStore((s) => s.authState)
  const hydrate = useAuthStore((s) => s.hydrate)
  const logout = useAuthStore((s) => s.logout)
  const bumpActivity = useAuthStore((s) => s.bumpActivity)
  const [warningOpen, setWarningOpen] = useState(false)
  const lastBumpRef = useRef(0)

  // pt.1 — hydrate once on mount.
  useEffect(() => {
    hydrate()
  }, [hydrate])

  // pt.3 — cross-tab sync. The `storage` event fires in OTHER tabs when
  // localStorage changes here — perfect for propagating logout / login.
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key !== 'token') return
      const currentAuth = useAuthStore.getState().authState
      if (e.newValue === null && currentAuth === 'authenticated') {
        // Another tab logged us out — silent redirect to /login.
        logout('multi_tab')
      } else if (e.newValue && currentAuth !== 'authenticated') {
        // Another tab logged in — sync the token into Zustand (hydrate reads
        // from state, not localStorage), then trigger the standard rehydrate.
        useAuthStore.setState({ token: e.newValue })
        hydrate()
      }
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [hydrate, logout])

  // pt.2 — activity tracking (debounced) + idle checker.
  useEffect(() => {
    if (authState !== 'authenticated') return

    const onActivity = () => {
      const now = Date.now()
      if (now - lastBumpRef.current < ACTIVITY_DEBOUNCE_MS) return
      lastBumpRef.current = now
      bumpActivity()
      if (warningOpen) setWarningOpen(false)
    }

    const events: Array<keyof WindowEventMap> = [
      'mousemove',
      'keydown',
      'scroll',
      'touchstart',
    ]
    events.forEach((e) => window.addEventListener(e, onActivity, { passive: true }))

    const timer = window.setInterval(() => {
      const idle = Date.now() - useAuthStore.getState().lastActivityAt
      if (idle >= INACTIVITY_MS) {
        logout('inactivity')
      } else if (idle >= INACTIVITY_MS - WARN_BEFORE_MS && !warningOpen) {
        setWarningOpen(true)
      }
    }, CHECK_INTERVAL_MS)

    return () => {
      events.forEach((e) => window.removeEventListener(e, onActivity))
      window.clearInterval(timer)
    }
  }, [authState, warningOpen, logout, bumpActivity])

  if (authState === 'loading') {
    return (
      <div className="min-h-screen bg-ivory flex items-center justify-center">
        <p className="text-navy/40 font-mono text-sm">…</p>
      </div>
    )
  }

  return (
    <>
      {children}
      {warningOpen && (
        <div
          className="fixed inset-0 bg-navy/50 backdrop-blur-sm z-50 flex items-center justify-center p-4"
          onClick={() => {
            bumpActivity()
            setWarningOpen(false)
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="bg-white rounded-2xl p-6 max-w-md w-full space-y-4 shadow-2xl"
          >
            <h3 className="font-display font-semibold text-lg text-navy">
              {t('auth.inactivityWarningTitle')}
            </h3>
            <p className="text-sm font-body text-navy/70">
              {t('auth.inactivityWarningBody')}
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => logout('inactivity')}
                className="text-sm font-body text-navy/60 hover:text-navy px-3 py-2"
              >
                {t('auth.logoutNow')}
              </button>
              <button
                onClick={() => {
                  bumpActivity()
                  setWarningOpen(false)
                }}
                className="bg-navy text-ivory font-display font-medium px-4 py-2 rounded-lg text-sm hover:bg-navy-mid"
              >
                {t('auth.stayLoggedIn')}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
