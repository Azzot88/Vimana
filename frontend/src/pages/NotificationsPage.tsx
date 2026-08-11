import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import ChannelsSection from '../components/ChannelsSection'
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
 * **Both halves live here** (owner's decision 2026-08-11). The first version
 * left channel connection on the profile, which put a person one navigation
 * away from the answer to their actual question: the matrix showed a column
 * they could not use, and the reason it was unusable was on another screen.
 * Connecting and choosing are one task from the outside, whatever they are
 * inside.
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

      {/* Connections first, then what travels down them — the order somebody
          reads this page in when nothing is arriving. Side by side on a
          desktop, stacked on a phone, and neither stretched: the matrix is
          three narrow columns, and across a full-width screen its checkboxes
          drift so far from their labels that a row is hard to read across. */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-start">
        <ChannelsSection />
        <NotificationMatrix />
      </div>
    </div>
  )
}
