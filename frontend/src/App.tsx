import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom'
import { useAuthStore } from './stores/auth'
import AuthBootstrap from './components/AuthBootstrap'
import Layout from './components/Layout'
import LandingPage from './pages/LandingPage'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import VerifyEmailPage from './pages/VerifyEmailPage'
import DashboardPage from './pages/DashboardPage'
import TripsPage from './pages/TripsPage'
import NewTripPage from './pages/NewTripPage'
import DealsPage from './pages/DealsPage'
import DealPage from './pages/DealPage'
import DealVaultPage from './pages/DealVaultPage'
import IdentityPage from './pages/IdentityPage'
import ProfileKeysPage from './pages/ProfileKeysPage'
import ProfilePage from './pages/ProfilePage'
import InvitePage from './pages/InvitePage'
import AcceptInvitePage from './pages/AcceptInvitePage'
import AdminDisputesPage from './pages/AdminDisputesPage'
import AdminNoticesPage from './pages/AdminNoticesPage'
import AdminUsersPage from './pages/AdminUsersPage'
import AdminVaultPage from './pages/AdminVaultPage'
import JoinDealPage from './pages/JoinDealPage'
import NotFoundPage from './pages/NotFoundPage'

function ProtectedRoute() {
  const token = useAuthStore((s) => s.token)
  if (!token) return <Navigate to="/login" replace />
  return <Outlet />
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthBootstrap>
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
      </AuthBootstrap>
    </BrowserRouter>
  )
}
