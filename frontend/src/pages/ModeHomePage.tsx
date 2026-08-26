import { Navigate } from 'react-router-dom'
import { useAuthStore } from '../stores/auth'
import Layout from '../components/Layout'
import DashboardPage from './DashboardPage'
import CarrierLandingPage from './CarrierLandingPage'
import SenderLandingPage from './SenderLandingPage'

/**
 * T_UX.23 — `/carrier` and `/send`: one address, two screens.
 *
 * A guest gets the audience landing. A signed-in account gets the panel. The
 * owner chose this over separate `/for-carriers` marketing addresses on
 * 2026-08-23, and it is the reason `Layout` grew a `children` prop: the landing
 * brings its own header and footer, so the app shell cannot be a parent route.
 *
 * **The URL follows the mode, not the other way round.** Visiting `/carrier`
 * while the account is in sender mode redirects to `/send` rather than
 * switching the mode. Switching would mean a stray link — a bookmark, a message
 * from a counterparty, a crawler — silently writing to `users.active_mode`, and
 * the mode decides what the whole panel and both navs show. Changing it stays a
 * deliberate act: `ModeSwitcher`, which now also moves the address.
 *
 * `AuthBootstrap` blocks rendering until hydration finishes, so `authState` is
 * never `loading` here and an authenticated account always has `user` — that
 * guarantee is the whole reason it exists (see its docstring), and this
 * component leans on it rather than re-checking.
 */
export default function ModeHomePage({ mode }: { mode: 'carrier' | 'sender' }) {
  const authState = useAuthStore((s) => s.authState)
  const user = useAuthStore((s) => s.user)

  if (authState !== 'authenticated' || !user) {
    return mode === 'carrier' ? <CarrierLandingPage /> : <SenderLandingPage />
  }

  // `can_carry` is checked as well as the mode: an account that cannot carry
  // has no business on the carrier panel even if `active_mode` says otherwise,
  // and that combination is reachable — the flag can be turned off in the admin
  // while the mode stays where the user left it.
  const effective = user.active_mode === 'carrier' && user.can_carry ? 'carrier' : 'sender'
  if (effective !== mode) {
    return <Navigate to={effective === 'carrier' ? '/carrier' : '/send'} replace />
  }

  return (
    <Layout>
      <DashboardPage />
    </Layout>
  )
}
