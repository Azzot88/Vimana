import { NavLink, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../stores/auth'

export default function Navbar() {
  const { user, logout } = useAuthStore()
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
              Dashboard
            </NavLink>
            <NavLink to="/trips" className={linkClass}>
              Рейсы
            </NavLink>
            <NavLink to="/deals" className={linkClass}>
              Сделки
            </NavLink>
            <NavLink to="/profile" className={linkClass}>
              Профиль
            </NavLink>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {user && (
            <span className="text-xs font-mono text-navy/50">
              {user.display_name}
            </span>
          )}
          <button
            onClick={handleLogout}
            className="text-xs font-body text-navy/50 hover:text-navy transition-colors"
          >
            Выйти
          </button>
        </div>
      </div>
    </nav>
  )
}
