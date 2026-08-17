import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { listTrips, type Trip } from '../api/trips'
import { usePrefs } from '../hooks/usePrefs'
import { useAuthStore } from '../stores/auth'
import InquiryPanel from '../components/InquiryPanel'
import MonoText from '../components/MonoText'
import UBAChip from '../components/UBAChip'

/** T_UX.18 — the person behind a trip.
 *
 *  A carrier's name used to be text. Handing a stranger a parcel is the moment
 *  somebody most wants to know who they are dealing with, and the answer was
 *  three numbers on a card and no way to ask a question. This page is the
 *  answer: what they fly, how active they are, and a way to write before
 *  committing to anything.
 *
 *  Built from the trip listing rather than a new profile endpoint — the trips a
 *  carrier has published are public already, and each row carries their name,
 *  activity level and key status. A separate endpoint would be a second source
 *  for the same facts.
 */
export default function CarrierPage() {
  const { t } = useTranslation()
  const { carrierId } = useParams<{ carrierId: string }>()
  const prefs = usePrefs()
  const me = useAuthStore((s) => s.user)

  const [trips, setTrips] = useState<Trip[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [chatTrip, setChatTrip] = useState<{ id: string; carrierName: string } | null>(
    null,
  )

  useEffect(() => {
    if (!carrierId) return
    setLoading(true)
    listTrips({ carrier_id: carrierId, limit: 50 })
      .then(({ data }) => setTrips(data.items))
      .catch(() => setError(t('common.errorGeneric') as string))
      .finally(() => setLoading(false))
  }, [carrierId, t])

  const first = trips[0]
  const isMe = me?.id === carrierId

  return (
    <div className="max-w-3xl mx-auto px-4 py-6 space-y-5">
      <Link
        to="/trips"
        className="text-xs font-body text-navy/40 hover:text-navy transition-colors"
      >
        ← {t('nav.trips')}
      </Link>

      <div className="bg-white rounded-card border border-navy/10 p-5">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-xl font-display font-semibold text-navy">
            {first?.carrier_name ?? t('carrier.unknown')}
          </h1>
          <UBAChip uba={first?.carrier_uba} level={first?.carrier_uba_level} />
          {first?.carrier_key_lost && (
            <span
              title={t('trips.keyLostHint') as string}
              className="text-xs font-body px-2 py-0.5 rounded bg-navy/10 text-navy/50"
            >
              {t('trips.keyLost')}
            </span>
          )}
        </div>
        <p className="mt-2 text-sm font-body text-navy/50">
          {t('carrier.tripsCount', { count: trips.length })}
        </p>
      </div>

      {error && <p className="text-sm font-body text-danger">{error}</p>}
      {loading && <p className="text-sm font-body text-navy/40">{t('common.loading')}</p>}

      {!loading && trips.length === 0 && (
        <p className="text-sm font-body text-navy/40">{t('carrier.noTrips')}</p>
      )}

      <div className="space-y-3">
        {trips.map((trip) => (
          <div
            key={trip.id}
            className="bg-white rounded-card border border-navy/10 p-4 flex flex-wrap items-center gap-x-4 gap-y-2"
          >
            <MonoText className="text-sm text-navy font-medium">
              {trip.origin} → {trip.destination}
            </MonoText>
            <MonoText className="text-xs text-navy/50">
              {prefs.dateTime(trip.depart_at)}
            </MonoText>
            <span className="text-xs font-body text-navy/50">
              {t('trips.capacity')}: {prefs.weight(trip.capacity)}
            </span>
            <span className="text-xs font-body text-navy/50">
              {t('trips.pricePerKg')}:{' '}
              {trip.price_per_kg
                ? `${trip.price_per_kg} ${trip.currency ?? 'USD'}`
                : t('trips.priceOnRequest')}
            </span>
            {trip.carriage_rules && (
              <span title={trip.carriage_rules} className="text-xs text-navy/50">
                📋 {t('trips.hasRules')}
              </span>
            )}
            {/* Writing to yourself is not a feature — the button is simply not
                there on your own page. */}
            {!isMe && (
              <button
                type="button"
                onClick={() =>
                  setChatTrip({ id: trip.id, carrierName: trip.carrier_name })
                }
                className="ml-auto px-3 py-1.5 rounded-field bg-cyan text-white text-xs font-body"
              >
                {t('carrier.write')}
              </button>
            )}
          </div>
        ))}
      </div>

      {chatTrip && (
        <InquiryPanel
          tripId={chatTrip.id}
          carrierName={chatTrip.carrierName}
          onClose={() => setChatTrip(null)}
        />
      )}
    </div>
  )
}
