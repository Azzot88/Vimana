import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

/**
 * T_UX.22 — «История и споры», the section for what has already happened.
 *
 * Both pages existed and neither had a home in the profile: history was reached
 * from the panel, disputes from a card on the showcase that T_UX.19 had only
 * put there because the profile had no navigation of its own. With a nav, the
 * two belong together — one asks what was carried, the other what went wrong
 * with it, and both are read rather than edited.
 *
 * The pages themselves are unchanged and keep their own addresses. This is the
 * way in, not a copy of them.
 */
export default function ProfileHistoryPage() {
  const { t } = useTranslation()

  const doors = [
    { to: '/history', titleKey: 'nav.history', descKey: 'profile.historyDesc' },
    { to: '/disputes', titleKey: 'nav.disputes', descKey: 'profile.disputesDesc' },
  ]

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-stretch">
      {doors.map((d) => (
        <Link
          key={d.to}
          to={d.to}
          className="block h-full bg-white rounded-card border border-navy/10 p-6 hover:border-cyan/40 transition-colors"
        >
          <h2 className="font-display font-semibold text-base text-navy">{t(d.titleKey)}</h2>
          <p className="text-xs font-body text-navy/50 mt-0.5">{t(d.descKey)}</p>
        </Link>
      ))}
    </div>
  )
}
