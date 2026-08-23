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
    <div className="space-y-4">
      {/* Connections first, then what travels down them — the order somebody
          reads this page in when nothing is arriving. Side by side on a wide
          screen, stacked otherwise, and neither stretched: the matrix is three
          narrow columns, and across a full-width screen its checkboxes drift so
          far from their labels that a row is hard to read across.
          T_UX.20 — `lg`, not `md`: the profile nav takes 13rem off the width,
          and the heading and the way back are the shell's job now. */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
        <ChannelsSection />
        <NotificationMatrix />
      </div>

      {/* T3.33 — said here because it is otherwise invisible. The language
          switcher in the header now sets the language of letters too, and a
          control with a second effect nobody mentions is one people discover by
          receiving mail they cannot read. */}
      <p className="text-xs font-body text-navy/40">
        {t('profile.matrix.languageNote')}
      </p>
    </div>
  )
}
