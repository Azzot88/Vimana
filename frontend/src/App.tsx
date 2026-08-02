import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom'
import { useAuthStore } from './stores/auth'
import AuthBootstrap from './components/AuthBootstrap'
import Layout from './components/Layout'
import MonoText from './components/MonoText'

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
import RegisterPage from './pages/RegisterPage'

const VerifyEmailPage = lazy(() => import('./pages/VerifyEmailPage'))
const DashboardPage = lazy(() => import('./pages/DashboardPage'))
const TripsPage = lazy(() => import('./pages/TripsPage'))
const NewTripPage = lazy(() => import('./pages/NewTripPage'))
const DealsPage = lazy(() => import('./pages/DealsPage'))
const DealPage = lazy(() => import('./pages/DealPage'))
const DealVaultPage = lazy(() => import('./pages/DealVaultPage'))
const IdentityPage = lazy(() => import('./pages/IdentityPage'))
const ProfileKeysPage = lazy(() => import('./pages/ProfileKeysPage'))
const ProfilePage = lazy(() => import('./pages/ProfilePage'))
const InvitePage = lazy(() => import('./pages/InvitePage'))
const AcceptInvitePage = lazy(() => import('./pages/AcceptInvitePage'))
const AdminDisputesPage = lazy(() => import('./pages/AdminDisputesPage'))
const AdminNoticesPage = lazy(() => import('./pages/AdminNoticesPage'))
const AdminUsersPage = lazy(() => import('./pages/AdminUsersPage'))
const AdminVaultPage = lazy(() => import('./pages/AdminVaultPage'))
const JoinDealPage = lazy(() => import('./pages/JoinDealPage'))
const NotFoundPage = lazy(() => import('./pages/NotFoundPage'))

function ProtectedRoute() {
  const token = useAuthStore((s) => s.token)
  if (!token) return <Navigate to="/login" replace />
  return <Outlet />
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
        <Suspense fallback={<RouteFallback />}>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/invite/:token" element={<AcceptInvitePage />} />
          <Route path="/join/deal/:token" element={<JoinDealPage />} />
          {/* T3.18 — public by design: this is what a counterparty opens
              *before* deciding to deal, and behind a login it would answer
              nobody's question. */}
          <Route path="/i/:npub" element={<IdentityPage />} />
          <Route element={<ProtectedRoute />}>
            <Route element={<Layout />}>
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/verify-email" element={<VerifyEmailPage />} />
              <Route path="/trips" element={<TripsPage />} />
              <Route path="/trips/new" element={<NewTripPage />} />
              <Route path="/deals" element={<DealsPage />} />
              <Route path="/deals/:dealId" element={<DealPage />} />
              <Route path="/deals/:dealId/vault" element={<DealVaultPage />} />
              <Route path="/profile" element={<ProfilePage />} />
              {/* T_UX.6 — its own path so banners, letters and the reader can
                  link straight to it. */}
              <Route path="/profile/keys" element={<ProfileKeysPage />} />
              <Route path="/invite" element={<InvitePage />} />
              <Route path="/admin/disputes" element={<AdminDisputesPage />} />
              <Route path="/admin/users" element={<AdminUsersPage />} />
              <Route path="/admin/notices" element={<AdminNoticesPage />} />
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
      </AuthBootstrap>
    </BrowserRouter>
  )
}
