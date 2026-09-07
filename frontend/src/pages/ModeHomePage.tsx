import { Navigate } from 'react-router-dom'
import { useAuthStore } from '../stores/auth'
import Layout from '../components/Layout'
import DashboardPage from './DashboardPage'
import TripsPage from './TripsPage'
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

  // T3.11.26 — a sender lands on the board, a carrier on the panel (owner's
  // decision 2026-09-07). The two modes want different first screens and always
  // did: a carrier opens the product to see what is happening with the trips
  // they published, a sender opens it to find one. The old shared panel gave the
  // sender a screen whose main content was a button called «Найти рейс» — one
  // click of ceremony in front of the thing they came for.
  //
  // The panel keeps its own address (`/dashboard`) for both, so the sender has
  // somewhere to go rather than somewhere to be sent.
  return (
    <Layout>{mode === 'carrier' ? <DashboardPage /> : <TripsPage />}</Layout>
  )
}
