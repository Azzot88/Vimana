import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { listTrips, type Trip } from '../api/trips'
import { useAuthStore } from '../stores/auth'
import { usePrefs } from '../hooks/usePrefs'
import MonoText from './MonoText'

/** T_UX.14 — everything this account has published, and the way to history.
 *
 *  The panel shows what is live. This is the other question — "what have I
 *  flown" — and it belongs where the rest of the account's own record lives
 *  rather than in the main navigation, which should carry only what needs
 *  doing today.
 */
export default function PublishedTripsSection() {
  const { t } = useTranslation()
  const prefs = usePrefs()
  const me = useAuthStore((s) => s.user)
  const [trips, setTrips] = useState<Trip[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!me?.id) return
    // History, not the board: withdrawn and flown trips belong here too.
      listTrips({ carrier_id: me.id, status: 'all', limit: 50 })
      .then(({ data }) => setTrips(data.items))
      .catch(() => setTrips([]))
      .finally(() => setLoading(false))
  }, [me?.id])

  // A sender who has never published anything does not need an empty shelf on
  // their profile; the section appears once there is something in it.
  if (!loading && trips.length === 0 && !me?.can_carry) return null

  return (
    <section className="bg-white rounded-card border border-navy/10 p-4 space-y-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-display font-semibold text-navy/50 uppercase tracking-wide">
          {t('profile.publishedTrips')}
        </p>
        <Link to="/history" className="text-xs font-body text-cyan">
          {t('nav.history')} →
        </Link>
      </div>

      {loading && <p className="text-xs font-body text-navy/40">{t('common.loading')}</p>}

      {!loading && trips.length === 0 && (
        <p className="text-xs font-body text-navy/40">{t('profile.noPublishedTrips')}</p>
      )}

      <div className="space-y-2">
        {trips.map((trip) => (
          <div
            key={trip.id}
            className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs border-b border-navy/5 pb-2 last:border-0"
          >
            <MonoText className="text-navy font-medium">
              {trip.origin} → {trip.destination}
            </MonoText>
            <MonoText className="text-navy/50">{prefs.date(trip.depart_at)}</MonoText>
            <span className="font-body text-navy/40">
              {prefs.weight(trip.capacity)}
            </span>
            <span className="ml-auto font-mono text-navy/40">{trip.status}</span>
          </div>
        ))}
      </div>
    </section>
  )
}
