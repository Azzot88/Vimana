import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import NotificationMatrix from '../components/NotificationMatrix'

/**
 * T3.32 — what reaches you, and where.
 *
 * A route rather than a block on the profile, for the same reason keys got one
 * in `T_UX.6`: the profile answers "who am I to the other party" — name,
 * avatar, activity, where a parcel goes. This answers a question asked at a
 * different moment, usually right after a notification arrived that somebody
 * did not want. Sitting between the contact list and the invite links, it was
 * a table nobody would look for.
 *
 * It also means the letters themselves can link here, which a tab in component
 * state could never do.
 *
 * The channel connections stay on the profile: connecting Telegram is part of
 * "how to reach me", which is a profile question. This page is only about which
 * of what reaches which connected channel.
 */
export default function NotificationsPage() {
  const { t } = useTranslation()

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <h1 className="font-display font-bold text-2xl text-navy">
          {t('profile.notifications')}
        </h1>
        <Link to="/profile" className="text-sm font-body text-cyan hover:underline">
          ← {t('profile.title')}
        </Link>
      </div>

      {/* Half width on a desktop: the table is three narrow columns, and
          stretched across a wide screen its switches drift so far from their
          labels that a row becomes hard to read across. */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-start">
        <NotificationMatrix />
      </div>
    </div>
  )
}
