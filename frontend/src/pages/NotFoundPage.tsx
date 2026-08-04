import { Link, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../stores/auth'
import MonoText from '../components/MonoText'

/**
 * T_UX.7 pt.1 — the page that was missing.
 *
 * The router had twenty routes and no catch-all, so a typo, a stale link or a
 * shared URL to a deleted deal fell through to a blank screen — the one moment
 * where a product most needs to say something.
 *
 * Two things it does that a default 404 does not:
 *
 * - **Shows the path that failed.** People arrive here from links they did not
 *   type, and the path is the only clue about who sent them somewhere wrong.
 * - **Offers the way back that fits the visitor.** A signed-in user wants their
 *   dashboard; a stranger who followed a link wants the front page. Sending
 *   both to the same place makes one of them wrong every time.
 *
 * Deliberately not: a joke, an illustration of a lost astronaut, or an
 * exclamation mark. Somebody's parcel may be on the other side of this link.
 */
export default function NotFoundPage() {
  const { t } = useTranslation()
  const { pathname } = useLocation()
  const token = useAuthStore((s) => s.token)

  return (
    <div className="min-h-[100dvh] bg-ivory flex items-center justify-center px-4">
      <div className="max-w-md w-full space-y-5">
        <MonoText className="text-xs text-muted">404</MonoText>
        <h1 className="font-display font-bold text-2xl text-navy text-balance">
          {t('notFound.title')}
        </h1>
        <p className="text-sm font-body text-muted">{t('notFound.body')}</p>

        <div className="bg-white rounded-card border border-navy/10 px-4 py-3">
          <p className="text-xs font-body text-muted mb-1">{t('notFound.pathLabel')}</p>
          <MonoText className="text-sm text-navy break-anywhere">{pathname}</MonoText>
        </div>

        <div className="flex flex-wrap gap-3">
          <Link
            to={token ? '/dashboard' : '/'}
            className="bg-navy text-ivory rounded-field px-4 py-2.5 text-sm font-body hover:bg-navy-mid transition-colors"
          >
            {token ? t('notFound.toDashboard') : t('notFound.toHome')}
          </Link>
          <Link
            to="/trips"
            className="border border-navy/20 rounded-field px-4 py-2.5 text-sm font-body text-navy hover:bg-navy/5 transition-colors"
          >
            {t('notFound.toTrips')}
          </Link>
        </div>
      </div>
    </div>
  )
}
