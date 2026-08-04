import { NavLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

const iconClass = 'w-5 h-5'

function IconHome() {
  return (
    <svg className={iconClass} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2h-4v-6H9v6H5a2 2 0 0 1-2-2z" />
    </svg>
  )
}

function IconTrips() {
  return (
    <svg className={iconClass} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17.8 19.2 16 11l3.5-3.5C21 6 21.5 4 21 3c-1-.5-3 0-4.5 1.5L13 8 4.8 6.2c-.5-.1-.9.1-1.1.5l-.3.5c-.2.5-.1 1 .3 1.3L9 12l-2 3H4l-1 1 3 2 2 3 1-1v-3l3-2 3.5 5.3c.3.4.8.5 1.3.3l.5-.2c.4-.3.6-.7.5-1.2z" />
    </svg>
  )
}

function IconDeals() {
  return (
    <svg className={iconClass} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20.59 13.41 13.42 20.58a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z" />
      <line x1="7" y1="7" x2="7.01" y2="7" />
    </svg>
  )
}

function IconProfile() {
  return (
    <svg className={iconClass} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  )
}

export default function BottomNav() {
  const { t } = useTranslation()

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `flex-1 flex flex-col items-center justify-center gap-0.5 py-2 min-h-[3.5rem] text-[10px] font-body transition-colors ${
      isActive ? 'text-cyan' : 'text-navy/50 hover:text-navy'
    }`

  return (
    <nav className="md:hidden fixed bottom-0 left-0 right-0 z-nav bg-white border-t border-navy/10 flex pb-[env(safe-area-inset-bottom)]">
      <NavLink to="/" end className={linkClass}>
        <IconHome />
        <span>{t('nav.dashboard')}</span>
      </NavLink>
      <NavLink to="/trips" className={linkClass}>
        <IconTrips />
        <span>{t('nav.trips')}</span>
      </NavLink>
      <NavLink to="/deals" className={linkClass}>
        <IconDeals />
        <span>{t('nav.deals')}</span>
      </NavLink>
      <NavLink to="/profile" className={linkClass}>
        <IconProfile />
        <span>{t('nav.profile')}</span>
      </NavLink>
    </nav>
  )
}
