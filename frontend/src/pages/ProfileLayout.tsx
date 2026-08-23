import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../stores/auth'
import { useBentoLayout } from '../hooks/useBentoLayout'
import MonoText from '../components/MonoText'
import { APP_VERSION } from '../version'

/**
 * T_UX.20 — the profile grew to 24 blocks across three routes and stopped
 * reading as anything. This is the shell: header, section nav, content.
 *
 * The sections are **routes, not tabs**, and that is the one thing here that is
 * not styling. `T_UX.6` gave keys their own path because the "2 codes left"
 * banner, the letter about a spent recovery code and the reader all link
 * straight to it; `T3.32` gave notifications one because the letters say
 * "change what reaches you" and have to mean somewhere. A tab lives in
 * component state and cannot be linked to.
 *
 * The door-cards that used to sit at the bottom of the profile existed only
 * because there was no navigation inside it. They are gone; their test ids
 * moved onto the nav links, which is the same contract in a different place.
 */

interface Section {
  to: string
  labelKey: string
  /** Only the index needs it: `/profile` prefix-matches every other section. */
  end?: boolean
  testId?: string
  roles?: Array<'arbiter' | 'superuser'>
}

const SECTIONS: Section[] = [
  { to: '/profile', labelKey: 'profile.nav.account', end: true },
  // T_UX.21 — second on purpose, above the circles: this is the section a
  // working carrier reopens, and the ones below it are read once. Order lives
  // here and nowhere else, so moving a section is moving a line.
  { to: '/profile/rules', labelKey: 'profile.nav.rules' },
  { to: '/profile/trust', labelKey: 'profile.nav.trust' },
  { to: '/profile/keys', labelKey: 'profile.nav.keys', testId: 'profile-keys-link' },
  { to: '/profile/prefs', labelKey: 'profile.nav.prefs' },
  {
    to: '/profile/notifications',
    labelKey: 'profile.nav.notifications',
    testId: 'profile-notifications-link',
  },
  {
    to: '/profile/admin',
    labelKey: 'profile.nav.admin',
    roles: ['arbiter', 'superuser'],
  },
]

export default function ProfileLayout() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const { user, logout } = useAuthStore()
  // T_UX.1 — the hook rather than `md:`, and for the case it was written for: a
  // phone in landscape is 932px wide, lands inside `md:`, and would get a 13rem
  // sidebar carved out of a screen somebody turned sideways to see more. It
  // also means one nav in the DOM instead of two hidden by CSS — no duplicate
  // landmark, and no test id matching twice.
  const layout = useBentoLayout()
  const isPhone = layout === 'phone'

  const role = user?.role
  const visible = SECTIONS.filter(
    (s) => !s.roles || ((role === 'arbiter' || role === 'superuser') && s.roles.includes(role)),
  )

  const isIndex = pathname === '/profile'

  /** The heading is the section, not the word "profile". Longest match wins so
   *  `/profile` does not claim `/profile/keys`; the index is the fallback. */
  const active =
    visible
      .filter((s) => !s.end && pathname.startsWith(s.to))
      .sort((a, b) => b.to.length - a.to.length)[0] ?? visible[0]

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const sidebarLinkClass = ({ isActive }: { isActive: boolean }) =>
    `block rounded-field px-3 py-2 text-sm font-body transition-colors ${
      isActive
        ? 'bg-cyan/10 text-cyan font-medium'
        : 'text-navy/60 hover:text-navy hover:bg-navy/5'
    }`

  const nav = (
    <nav aria-label={t('profile.nav.label') as string} className="space-y-1">
      {visible.map((s) => (
        <NavLink
          key={s.to}
          to={s.to}
          end={s.end}
          data-testid={s.testId}
          className={sidebarLinkClass}
        >
          {t(s.labelKey)}
        </NavLink>
      ))}
    </nav>
  )

  return (
    <div className="space-y-6">
      {/* The `h1` is the section, with the profile as an eyebrow above it. The
          other way round — «Профиль» as the heading and the section title
          inside the content — would put an `h1` and an `h2` over the same
          thing, and every card in every section already starts at `h2`. This
          keeps one heading level per screen without touching twenty
          components. */}
      <div>
        <p className="text-xs font-display font-semibold text-navy/50 uppercase tracking-wide">
          {t('profile.title')}
        </p>
        <h1 className="font-display font-bold text-2xl text-navy">{t(active.labelKey)}</h1>
      </div>

      {isPhone ? (
        <div className="space-y-4">
          {/* 13rem of chrome beside a 375px screen is not a layout, so the nav
              becomes a list — and only on the index, because repeating it above
              every section is six rows of furniture before the thing somebody
              came for. Sub-sections get the way back instead, which is the
              pattern `/profile/keys` already used. */}
          {isIndex ? (
            nav
          ) : (
            <Link to="/profile" className="text-sm font-body text-cyan hover:underline">
              ← {t('profile.nav.account')}
            </Link>
          )}
          <Outlet />
        </div>
      ) : (
        <div className="grid grid-cols-[13rem_minmax(0,1fr)] gap-6 items-start">
          {/* Sticky so a long section does not scroll the panel out of reach.
              `top-20` clears the sticky app header, which is 3.5rem tall. */}
          <div className="sticky top-20">{nav}</div>
          <div className="min-w-0 space-y-4">
            <Outlet />
          </div>
        </div>
      )}

      <div className="flex items-center justify-between pt-2">
        <button
          onClick={handleLogout}
          className="text-sm font-body text-navy/40 hover:text-navy transition-colors"
        >
          {t('profile.logout')}
        </button>
        <MonoText className="text-xs text-navy/20">v{APP_VERSION}</MonoText>
      </div>
    </div>
  )
}
