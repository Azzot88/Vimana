import { Navigate } from 'react-router-dom'
import AdminPanelSection from '../components/AdminPanelSection'
import { isStaff } from '../lib/permissions'
import { useAuthStore } from '../stores/auth'

/**
 * T_UX.20 — «Администрирование», the seventh section, and only for staff.
 *
 * The nav already filters this item out by role, but a hidden link is not a
 * guard: the address is guessable and used to be reachable. `AdminPanelSection`
 * renders nothing for anyone else, so without the redirect a typed URL would
 * land on an empty section that looks like a broken page rather than a closed
 * door. The real enforcement is the backend permission on each admin route —
 * this only decides what the profile shows.
 */
export default function ProfileAdminPage() {
  const user = useAuthStore((s) => s.user)

  // T3.11.02 — staff, not arbiters: an editor holds neither of the two roles
  // this used to name, and would have been redirected away from the section
  // that exists for them.
  if (!isStaff(user)) {
    return <Navigate to="/profile" replace />
  }

  return (
    <div className="space-y-4">
      <AdminPanelSection />
    </div>
  )
}
