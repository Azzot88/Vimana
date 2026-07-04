import { NavLink, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../stores/auth'
import LanguageSwitcher from './LanguageSwitcher'

export default function Navbar() {
  const { user, logout } = useAuthStore()
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
    <nav className="bg-white border-b border-navy/10 sticky top-0 z-10">
      <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
        <div className="flex items-center gap-6">
          <span className="font-display font-bold text-navy text-lg tracking-tight">
            Vimana
          </span>
          <div className="flex items-center gap-4">
            <NavLink to="/" end className={linkClass}>
              {t('nav.dashboard')}
            </NavLink>
            <NavLink to="/trips" className={linkClass}>
              {t('nav.trips')}
            </NavLink>
            <NavLink to="/deals" className={linkClass}>
              {t('nav.deals')}
            </NavLink>
            <NavLink to="/profile" className={linkClass}>
              {t('nav.profile')}
            </NavLink>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <LanguageSwitcher />
          {user && (
            <span className="text-xs font-mono text-navy/50">
              {user.display_name}
            </span>
          )}
          <button
            onClick={handleLogout}
            className="text-xs font-body text-navy/50 hover:text-navy transition-colors"
          >
            {t('nav.logout')}
          </button>
        </div>
      </div>
    </nav>
  )
}
