import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom'
import { useAuthStore } from './stores/auth'
import AuthBootstrap from './components/AuthBootstrap'
import Layout from './components/Layout'
import MonoText from './components/MonoText'
import RouteErrorBoundary from './components/ErrorBoundary'

/**
 * T_UX.7 pt.2 — the three pages a stranger can reach are bundled eagerly; every
 * screen behind a session loads when it is first opened.
 *
 * The build warned that the main chunk had passed 500 kB and the warning had
 * been living there long enough to read as decoration. It mattered more once
 * the landing became a real front door: a visitor who only ever reads it was
 * downloading the arbiter's vault screen to do so.
 */
import LandingPage from './pages/LandingPage'
import LoginPage from './pages/LoginPage'

const VerifyEmailPage = lazy(() => import('./pages/VerifyEmailPage'))
/** T_UX.23 — `/carrier` and `/send` are one chunk each: a guest gets the
 *  landing out of it, a signed-in account gets the panel. Splitting them would
 *  mean a second request at the exact moment the answer is already known. */
const ModeHomePage = lazy(() => import('./pages/ModeHomePage'))
const BusinessLandingPage = lazy(() => import('./pages/BusinessLandingPage'))
const TripsPage = lazy(() => import('./pages/TripsPage'))
const NewTripPage = lazy(() => import('./pages/NewTripPage'))
const DealsPage = lazy(() => import('./pages/DealsPage'))
const DealPage = lazy(() => import('./pages/DealPage'))
const DealVaultPage = lazy(() => import('./pages/DealVaultPage'))
const IdentityPage = lazy(() => import('./pages/IdentityPage'))
const NotificationsPage = lazy(() => import('./pages/NotificationsPage'))
const ProfileKeysPage = lazy(() => import('./pages/ProfileKeysPage'))
const ProfileLayout = lazy(() => import('./pages/ProfileLayout'))
const ProfilePage = lazy(() => import('./pages/ProfilePage'))
const ProfileRulesPage = lazy(() => import('./pages/ProfileRulesPage'))
const ProfileHistoryPage = lazy(() => import('./pages/ProfileHistoryPage'))
const ProfileTrustPage = lazy(() => import('./pages/ProfileTrustPage'))
const ProfilePrefsPage = lazy(() => import('./pages/ProfilePrefsPage'))
const ProfileAdminPage = lazy(() => import('./pages/ProfileAdminPage'))
const InvitePage = lazy(() => import('./pages/InvitePage'))
const AcceptInvitePage = lazy(() => import('./pages/AcceptInvitePage'))
const AdminNoticesPage = lazy(() => import('./pages/AdminNoticesPage'))
const AdminEmailPage = lazy(() => import('./pages/AdminEmailPage'))
const AdminUsersPage = lazy(() => import('./pages/AdminUsersPage'))
const AdminRolesPage = lazy(() => import('./pages/AdminRolesPage'))
const AdminRulesPage = lazy(() => import('./pages/AdminRulesPage'))
const RulesPage = lazy(() => import('./pages/RulesPage'))
const AdminVaultPage = lazy(() => import('./pages/AdminVaultPage'))
const AdminParamsPage = lazy(() => import('./pages/AdminParamsPage'))
const CarrierPage = lazy(() => import('./pages/CarrierPage'))
const DisputesPage = lazy(() => import('./pages/DisputesPage'))
const JoinDealPage = lazy(() => import('./pages/JoinDealPage'))
const NotFoundPage = lazy(() => import('./pages/NotFoundPage'))
const ResetPasswordPage = lazy(() => import('./pages/ResetPasswordPage'))
const WelcomePage = lazy(() => import('./pages/WelcomePage'))

function ProtectedRoute() {
  const token = useAuthStore((s) => s.token)
  if (!token) return <Navigate to="/login" replace />
  return <Outlet />
}

/** T_UX.23 — `/dashboard` kept as a redirect rather than deleted.
 *
 *  It is linked from letters, from the landing header, from `WelcomePage` and
 *  from three years of muscle memory. A dead address is a worse answer than a
 *  redirect, exactly as with `/register` above. */
function DashboardRedirect() {
  const user = useAuthStore((s) => s.user)
  const to = user?.active_mode === 'carrier' && user.can_carry ? '/carrier' : '/send'
  return <Navigate to={to} replace />
}

/** Deliberately quiet: a chunk fetch on a warm connection is over before a
 *  spinner would finish appearing, and a flashing spinner reads as a fault. */
function RouteFallback() {
  return (
    <div className="flex min-h-[40vh] items-center justify-center">
      <MonoText className="text-sm text-navy/30">·</MonoText>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthBootstrap>
        {/* T_UX.11 — inside the router (it keys off the path) and outside
            `Suspense` (a chunk that fails to load rejects the suspended
            promise, and only a boundary above it ever sees that). */}
        <RouteErrorBoundary>
        <Suspense fallback={<RouteFallback />}>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          {/* T_UX.23 — the three audiences. `/carrier` and `/send` sit outside
              `ProtectedRoute` on purpose: to a guest they are marketing pages,
              to a signed-in account they are the panel, and `ModeHomePage`
              makes that call. `/business` has no panel behind it — there is no
              business mode, only `carrier | sender`. */}
          <Route path="/carrier" element={<ModeHomePage mode="carrier" />} />
          <Route path="/send" element={<ModeHomePage mode="sender" />} />
          <Route path="/business" element={<BusinessLandingPage />} />
          {/* T3.11.03 — the public rules directory. Category first: people
              search for "how do I take a painting out of Russia", not for
              "what may leave Russia". Open to everybody, by design. */}
          <Route
            path="/rules/:category/:direction/:country"
            element={<RulesPage />}
          />
          <Route path="/login" element={<LoginPage />} />
          {/* T3.28 pt.3 — `/register` now goes to the same door. The
              password form is gone from the product: one field, a code, and an
              account either exists or comes into being. The route is kept
              rather than deleted because links to it are three years of chat
              history and two emails, and a dead link is a worse answer than a
              redirect. */}
          <Route path="/register" element={<Navigate to="/login" replace />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />
          <Route path="/invite/:token" element={<AcceptInvitePage />} />
          <Route path="/join/deal/:token" element={<JoinDealPage />} />
          {/* T3.18 — public by design: this is what a counterparty opens
              *before* deciding to deal, and behind a login it would answer
              nobody's question. */}
          <Route path="/i/:npub" element={<IdentityPage />} />
          <Route element={<ProtectedRoute />}>
            {/* T3.28 pt.2 — protected but outside `Layout`: the account exists
                and is signed in, but a navigation bar around a single question
                invites wandering off before answering it. */}
            <Route path="/welcome" element={<WelcomePage />} />
            <Route path="/dashboard" element={<DashboardRedirect />} />
            <Route element={<Layout />}>
              <Route path="/verify-email" element={<VerifyEmailPage />} />
              <Route path="/trips" element={<TripsPage />} />
              <Route path="/trips/new" element={<NewTripPage />} />
              {/* T_UX.18 — the deals tab became history: a finished delivery is
                  something you look up, not something you navigate by. `/deals`
                  stays as the entry point old links point at. */}
              <Route path="/history" element={<DealsPage />} />
              <Route path="/deals" element={<Navigate to="/history" replace />} />
              <Route path="/disputes" element={<DisputesPage />} />
              <Route path="/carriers/:carrierId" element={<CarrierPage />} />
              <Route path="/deals/:dealId" element={<DealPage />} />
              <Route path="/deals/:dealId/vault" element={<DealVaultPage />} />
              {/* T_UX.20 — the profile is seven sections behind one shell, and
                  every one of them is a real path. Nesting rather than tabs is
                  the whole point: `T_UX.6` and `T3.32` gave keys and
                  notifications their own addresses because banners, letters and
                  the reader link straight to them, and both addresses are
                  unchanged here. */}
              <Route path="/profile" element={<ProfileLayout />}>
                <Route index element={<ProfilePage />} />
                <Route path="rules" element={<ProfileRulesPage />} />
                {/* T_UX.21 — «Уровень активности» folded into the account, so
                    the address retires rather than disappears. Cheap to keep:
                    nothing outside the app links here (the section existed for
                    a day and no letter mentions it), but a bookmark from that
                    day should land on the score rather than on the 404. */}
                <Route path="activity" element={<Navigate to="/profile" replace />} />
                <Route path="trust" element={<ProfileTrustPage />} />
                {/* T_UX.6 — its own path so banners, letters and the reader can
                    link straight to it. */}
                <Route path="keys" element={<ProfileKeysPage />} />
                <Route path="history" element={<ProfileHistoryPage />} />
                <Route path="prefs" element={<ProfilePrefsPage />} />
                {/* T3.32 — a path so a letter can say «change what reaches you»
                    and mean somewhere in particular. */}
                <Route path="notifications" element={<NotificationsPage />} />
                <Route path="admin" element={<ProfileAdminPage />} />
              </Route>
              <Route path="/invite" element={<InvitePage />} />
              {/* T_UX.19 — merged into `/disputes`; the old link keeps working. */}
              <Route path="/admin/disputes" element={<Navigate to="/disputes" replace />} />
              <Route path="/admin/users" element={<AdminUsersPage />} />
              <Route path="/admin/role-offers" element={<AdminRolesPage />} />
              <Route path="/admin/rules" element={<AdminRulesPage />} />
              <Route path="/admin/notices" element={<AdminNoticesPage />} />
              <Route path="/admin/email" element={<AdminEmailPage />} />
              <Route path="/admin/params" element={<AdminParamsPage />} />
              <Route path="/admin/deals/:dealId/vault" element={<AdminVaultPage />} />
            </Route>
          </Route>
          {/* T_UX.7 pt.1 — the catch-all that was missing. Outside the
              protected block on purpose: a stranger following a dead link
              should be told the page does not exist, not bounced to a login
              that implies it does. */}
          <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </Suspense>
        </RouteErrorBoundary>
      </AuthBootstrap>
    </BrowserRouter>
  )
}
