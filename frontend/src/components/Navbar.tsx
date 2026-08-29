import { Link, NavLink, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../stores/auth'
import { isSuperuser } from '../lib/permissions'
import LanguageSwitcher from './LanguageSwitcher'
import ModeSwitcher from './ModeSwitcher'

export default function Navbar() {
  const { user, logout } = useAuthStore()
  // Reactive, not `getState()`: the nav has to change the moment the mode does.
  const isCarrierMode = user?.active_mode === 'carrier'
  // T_UX.23 — the panel lives at two addresses now. Pointing this at
  // `/dashboard` would still work (it redirects), but the link would never
  // light up as active, because the address it names is one nobody ever stays
  // on.
  const panelHref = isCarrierMode ? '/carrier' : '/send'
  const { t } = useTranslation()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `text-sm font-body font-medium transition-colors ${
      isActive ? 'text-cyan' : 'text-navy/60 hover:text-navy'
    }`

  return (
    <nav className="bg-white border-b border-navy/10 sticky top-0 z-nav">
      <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between gap-3">
        <div className="flex items-center gap-6">
          <Link
            to="/"
            className="font-display font-bold text-navy text-lg tracking-tight hover:text-cyan transition-colors"
          >
            Vimana
          </Link>
          <div className="hidden md:flex items-center gap-4">
            <NavLink to={panelHref} end className={linkClass}>
              {t('nav.dashboard')}
            </NavLink>
            {/* T_UX.18 — the two modes want different boards. A carrier's own
                trips and their controls live on the panel; other carriers'
                trips are not their business. A sender needs the opposite: the
                board of what is available to book. */}
            {!isCarrierMode && (
              <NavLink to="/trips" className={linkClass}>
                {t('nav.trips')}
              </NavLink>
            )}
            {/* T3.11.03 — the directory belongs in the signed-in nav as much
                as on the landing: the question "what do I need to get this
                through" arrives while somebody is already arranging a
                shipment, not before they have an account. */}
            <NavLink to="/rules" className={linkClass}>
              {t('nav.rules')}
            </NavLink>
            <NavLink to="/profile" className={linkClass}>
              {t('nav.profile')}
            </NavLink>
            {isSuperuser(user) && (
              <>
                <NavLink to="/admin/users" className={linkClass}>
                  {t('nav.users')}
                </NavLink>
                <NavLink to="/admin/notices" className={linkClass}>
                  {t('nav.notices')}
                </NavLink>
              </>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 md:gap-3">
          <ModeSwitcher />
          <LanguageSwitcher />
          {user && (
            <span className="hidden md:inline text-xs font-mono text-navy/50">
              {user.display_name}
            </span>
          )}
          <button
            onClick={handleLogout}
            className="hidden md:inline text-xs font-body text-navy/50 hover:text-navy transition-colors"
          >
            {t('nav.logout')}
          </button>
        </div>
      </div>
    </nav>
  )
}
