import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { listDeals, type Deal } from '../api/deals'
import { cancelTrip, listTrips, type Trip } from '../api/trips'
import { listMyInquiries, type Inquiry } from '../api/inquiry'
import { useAuthStore } from '../stores/auth'
import { usePrefs } from '../hooks/usePrefs'
import MonoText from '../components/MonoText'
import StatusBadge from '../components/StatusBadge'

/** T_UX.19 — the panel answers one question, and which one depends on the mode.
 *
 *  It used to answer both at once: a carrier saw the deals they were sending
 *  and a sender saw a "trips I carry" block they would never fill. Everything
 *  was on screen, so nothing was.
 *
 *  Carrying: **what am I flying, and who is asking about it.** Sending: **where
 *  are my parcels.** Anything that is neither — the finished deals, the whole
 *  public board — is one link away, not on the panel.
 */
const ACTIVE = ['matched', 'accepted', 'in_transit', 'delivered', 'confirmed']

export default function DashboardPage() {
  const { t } = useTranslation()
  const prefs = usePrefs()
  const user = useAuthStore((s) => s.user)

  const [deals, setDeals] = useState<Deal[]>([])
  const [trips, setTrips] = useState<Trip[]>([])
  const [inquiries, setInquiries] = useState<Inquiry[]>([])
  const [loading, setLoading] = useState(true)
  const [busyTrip, setBusyTrip] = useState<string | null>(null)
  const [error, setError] = useState('')

  const load = async () => {
    if (!user?.id) return
    try {
      const [dealsRes, tripsRes, inqRes] = await Promise.all([
        listDeals(),
        // `all`, then filtered below: the public board returns only `open`,
        // so asking without a status would silently drop matched trips — the
        // ones with somebody already counting on them.
        listTrips({ carrier_id: user.id, status: 'all', limit: 50 }),
        listMyInquiries().catch(() => ({ data: [] as Inquiry[] })),
      ])
      setDeals(dealsRes.data.items)
      setTrips(tripsRes.data.items)
      setInquiries(inqRes.data)
    } catch {
      setError(t('common.errorGeneric') as string)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <MonoText className="text-navy/40 text-sm">{t('common.loading')}</MonoText>
      </div>
    )
  }

  const isCarrier = user?.active_mode === 'carrier'
  // T1.24 — visual mode signal without labelling the mode.
  const accentBar = isCarrier
    ? 'bg-gradient-to-r from-cyan/40 via-cyan/20 to-transparent'
    : 'bg-gradient-to-r from-amber/40 via-amber/20 to-transparent'

  const liveTrips = trips.filter((tr) => tr.status === 'open' || tr.status === 'matched')
  const carrying = deals.filter(
    (d) => d.carrier_id === user?.id && ACTIVE.includes(d.status),
  )
  const sending = deals.filter(
    (d) => d.sender_id === user?.id && ACTIVE.includes(d.status),
  )
  const inquiriesFor = (tripId: string) =>
    inquiries.filter((i) => i.trip_id === tripId).length

  const withdraw = async (tripId: string) => {
    setBusyTrip(tripId)
    setError('')
    try {
      await cancelTrip(tripId)
      await load()
    } catch {
      setError(t('dashboard.withdrawFailed') as string)
    } finally {
      setBusyTrip(null)
    }
  }

  const dealRow = (deal: Deal) => (
    <Link
      key={deal.id}
      to={`/deals/${deal.id}`}
      className="bg-white rounded-card border border-navy/10 p-4 hover:border-cyan/40 transition-colors flex items-center justify-between gap-3"
    >
      <div className="space-y-1 min-w-0">
        <MonoText className="text-sm text-navy font-medium">
          {deal.origin} → {deal.destination}
        </MonoText>
        <p className="text-xs font-body text-navy/50 truncate">
          {deal.cargo_description}
        </p>
      </div>
      <StatusBadge status={deal.status} />
    </Link>
  )

  return (
    <div className="space-y-8">
      <div className={`h-1.5 rounded-full ${accentBar}`} />

      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="flex items-center gap-3">
          <span aria-hidden="true" className="text-2xl">
            {isCarrier ? '✈️' : '📦'}
          </span>
          <h1 className="font-display font-bold text-xl sm:text-2xl text-navy">
            {user ? t('dashboard.welcome', { name: user.display_name }) : 'Dashboard'}
          </h1>
        </div>
        {/* T3.19 — an action a retired identity cannot complete is hidden, not
            offered and then refused. */}
        {isCarrier && user?.can_carry && !user?.key_lost && (
          <Link
            to="/trips/new"
            className="bg-cyan text-white font-display font-medium px-4 py-3 min-h-[2.75rem] rounded-field text-sm hover:opacity-90 transition-opacity flex items-center"
          >
            {t('dashboard.publishTrip')}
          </Link>
        )}
        {!isCarrier && (
          <Link
            to="/trips"
            className="bg-amber text-white font-display font-medium px-4 py-3 min-h-[2.75rem] rounded-field text-sm hover:opacity-90 transition-opacity flex items-center"
          >
            {t('dashboard.findTrip')}
          </Link>
        )}
      </div>

      {error && <p className="text-xs font-mono text-danger">{error}</p>}

      {isCarrier ? (
        <>
          <section>
            <h2 className="font-display font-semibold text-lg text-navy mb-3">
              {t('dashboard.myTrips')}
            </h2>
            {liveTrips.length === 0 ? (
              <div className="bg-white rounded-card border border-navy/10 p-6 text-center">
                <p className="text-sm font-body text-navy/40">
                  {t('dashboard.noTrips')}
                </p>
                {!user?.key_lost && (
                  <Link
                    to="/trips/new"
                    className="inline-block mt-3 text-sm text-cyan hover:underline font-body"
                  >
                    {t('dashboard.publishFirst')}
                  </Link>
                )}
              </div>
            ) : (
              <div className="grid gap-3">
                {liveTrips.map((trip) => {
                  const asks = inquiriesFor(trip.id)
                  return (
                    <div
                      key={trip.id}
                      className="bg-white rounded-card border border-navy/10 p-4 space-y-2"
                    >
                      <div className="flex flex-wrap items-center gap-3">
                        <MonoText className="text-sm text-navy font-medium">
                          {trip.origin} → {trip.destination}
                        </MonoText>
                        <MonoText className="text-xs text-navy/50">
                          {prefs.dateTime(trip.depart_at)}
                        </MonoText>
                        <span className="text-xs font-mono text-navy/40 ml-auto">
                          {trip.status}
                        </span>
                      </div>
                      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs font-body text-navy/50">
                        <span>
                          {t('trips.capacity')}: {prefs.weight(trip.capacity)}
                        </span>
                        <span>
                          {t('trips.pricePerKg')}:{' '}
                          {trip.price_per_kg
                            ? `${trip.price_per_kg} ${trip.currency ?? 'USD'}`
                            : t('trips.priceOnRequest')}
                        </span>
                        {/* Who is asking about this trip. A published trip with
                            unanswered questions is the one thing on this screen
                            that needs doing today. */}
                        {asks > 0 && (
                          <span className="text-cyan font-medium">
                            💬 {t('dashboard.inquiries', { count: asks })}
                          </span>
                        )}
                      </div>
                      <div className="flex gap-3 pt-1">
                        <Link
                          to={`/carriers/${trip.carrier_id}`}
                          className="text-xs font-body text-navy/40 hover:text-navy"
                        >
                          {t('dashboard.viewAsSender')}
                        </Link>
                        {trip.status === 'open' && (
                          <button
                            type="button"
                            disabled={busyTrip === trip.id}
                            onClick={() => void withdraw(trip.id)}
                            className="text-xs font-body text-danger hover:underline disabled:opacity-50 ml-auto"
                          >
                            {busyTrip === trip.id ? '...' : t('dashboard.withdraw')}
                          </button>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </section>

          {carrying.length > 0 && (
            <section>
              <h2 className="font-display font-semibold text-lg text-navy mb-3">
                {t('dashboard.carryingNow')}
              </h2>
              <div className="grid gap-3">{carrying.map(dealRow)}</div>
            </section>
          )}
        </>
      ) : (
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-display font-semibold text-lg text-navy">
              {t('dashboard.myShipments')}
            </h2>
            <Link to="/history" className="text-xs text-cyan hover:underline font-body">
              {t('nav.history')}
            </Link>
          </div>
          {sending.length === 0 ? (
            <div className="bg-white rounded-card border border-navy/10 p-6 text-center">
              <p className="text-sm font-body text-navy/40">
                {t('dashboard.noShipments')}
              </p>
              <Link
                to="/trips"
                className="inline-block mt-3 text-sm text-cyan hover:underline font-body"
              >
                {t('dashboard.findTrip')}
              </Link>
            </div>
          ) : (
            <div className="grid gap-3">{sending.map(dealRow)}</div>
          )}
        </section>
      )}
    </div>
  )
}
