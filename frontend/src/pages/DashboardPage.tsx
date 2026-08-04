import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../stores/auth'
import { me } from '../api/auth'
import { listDeals, type Deal } from '../api/deals'
import { listTrips, type Trip } from '../api/trips'
import StatusBadge from '../components/StatusBadge'
import MonoText from '../components/MonoText'
import { APP_VERSION } from '../version'

export default function DashboardPage() {
  const { user, setAuth, token } = useAuthStore()
  const { t, i18n } = useTranslation()
  const [deals, setDeals] = useState<Deal[]>([])
  const [trips, setTrips] = useState<Trip[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      try {
        if (!user && token) {
          const { data: userData } = await me()
          setAuth(userData, token)
        }
        const [dealsRes, tripsRes] = await Promise.all([listDeals(), listTrips()])
        setDeals(dealsRes.data.items)
        setTrips(tripsRes.data.items)
      } catch {
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  const currentUser = user
  const myTrips = trips.filter((t) => t.carrier_id === currentUser?.id)
  const asCarrierDeals = deals.filter((d) => d.carrier_id === currentUser?.id)
  const asSenderDeals = deals.filter((d) => d.sender_id === currentUser?.id)
  const activeDeals = deals.filter((d) =>
    ['matched', 'accepted', 'in_transit', 'delivered'].includes(d.status)
  )

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <MonoText className="text-muted text-sm">{t('common.loading')}</MonoText>
      </div>
    )
  }

  const isCarrier = currentUser?.active_mode === 'carrier'
  // T1.24 — visual mode signal without labelling the mode. Cyan sky for carrier,
  // amber runway for sender. The mode itself is understood from context, not text.
  const accentBar = isCarrier
    ? 'bg-gradient-to-r from-cyan/40 via-cyan/20 to-transparent'
    : 'bg-gradient-to-r from-amber/40 via-amber/20 to-transparent'
  const modeIcon = isCarrier ? '✈️' : '📦'

  return (
    <div className="space-y-8">
      <div className={`h-1.5 rounded-full ${accentBar}`} />
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="flex items-center gap-3">
          <span aria-hidden="true" className="text-2xl">{modeIcon}</span>
          <h1 className="font-display font-bold text-xl sm:text-2xl text-navy">
            {currentUser
              ? t('dashboard.welcome', { name: currentUser.display_name })
              : 'Dashboard'}
          </h1>
        </div>
        {/* T3.19 — an action a retired identity cannot complete is hidden, not
            offered and then refused: the server answers 403 to publishing
            without a key, and a button whose only outcome is that message is a
            trap, not a feature. */}
        {isCarrier && currentUser?.can_carry && !currentUser?.key_lost && (
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

      {activeDeals.length > 0 && (
        <section>
          <h2 className="font-display font-semibold text-lg text-navy mb-3">{t('dashboard.activeDeals')}</h2>
          <div className="grid gap-3">
            {activeDeals.map((deal) => (
              <Link
                key={deal.id}
                to={`/deals/${deal.id}`}
                className="bg-white rounded-card border border-navy/10 p-4 hover:border-cyan/40 transition-colors flex items-center justify-between"
              >
                <div className="space-y-1">
                  <MonoText className="text-sm text-navy font-medium">
                    {deal.origin} → {deal.destination}
                  </MonoText>
                  <p className="text-xs font-body text-muted">
                    {deal.carrier_id === currentUser?.id ? t('dashboard.carrier') : t('dashboard.sender')} · {deal.cargo_description}
                  </p>
                </div>
                <StatusBadge status={deal.status} />
              </Link>
            ))}
          </div>
        </section>
      )}

      {(currentUser?.active_mode === 'carrier') && (
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-display font-semibold text-lg text-navy">{t('dashboard.iCarry')}</h2>
            <Link to="/trips" className="text-xs text-link hover:underline font-body">
              {t('dashboard.allTrips')}
            </Link>
          </div>
          {myTrips.length === 0 ? (
            <div className="bg-white rounded-card border border-navy/10 p-6 text-center">
              <p className="text-sm font-body text-muted">{t('dashboard.noTrips')}</p>
              {!currentUser?.key_lost && (
                <Link
                  to="/trips/new"
                  className="inline-block mt-3 text-sm text-link hover:underline font-body"
                >
                  {t('dashboard.publishFirst')}
                </Link>
              )}
            </div>
          ) : (
            <div className="grid gap-3">
              {myTrips.slice(0, 3).map((trip) => (
                <div
                  key={trip.id}
                  className="bg-white rounded-card border border-navy/10 p-4"
                >
                  <div className="flex items-center justify-between">
                    <MonoText className="text-sm text-navy font-medium">
                      {trip.origin} → {trip.destination}
                    </MonoText>
                    <MonoText className="text-xs text-muted">
                      {new Date(trip.depart_at).toLocaleDateString(i18n.language)}
                    </MonoText>
                  </div>
                  <p className="text-xs font-body text-muted mt-1">
                    {t('trips.capacity')}: {trip.capacity} {t('trips.kg')}
                  </p>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-display font-semibold text-lg text-navy">
            {(currentUser?.active_mode === 'carrier') ? t('dashboard.myCargoCarrier') : t('dashboard.myCargoSender')}
          </h2>
          <Link to="/deals" className="text-xs text-link hover:underline font-body">
            {t('dashboard.allDeals')}
          </Link>
        </div>
        {asCarrierDeals.length === 0 && asSenderDeals.length === 0 ? (
          <div className="bg-white rounded-card border border-navy/10 p-6 text-center">
            <p className="text-sm font-body text-muted">{t('dashboard.noDeals')}</p>
            <Link
              to="/trips"
              className="inline-block mt-3 text-sm text-link hover:underline font-body"
            >
              {t('dashboard.findTrip')}
            </Link>
          </div>
        ) : (
          <div className="grid gap-3">
            {[...asCarrierDeals, ...asSenderDeals].slice(0, 3).map((deal) => (
              <Link
                key={deal.id}
                to={`/deals/${deal.id}`}
                className="bg-white rounded-card border border-navy/10 p-4 hover:border-cyan/40 transition-colors flex items-center justify-between"
              >
                <div className="space-y-1">
                  <MonoText className="text-sm text-navy font-medium">
                    {deal.origin} → {deal.destination}
                  </MonoText>
                  <p className="text-xs font-body text-muted">{deal.cargo_description}</p>
                </div>
                <StatusBadge status={deal.status} />
              </Link>
            ))}
          </div>
        )}
      </section>

      {!(currentUser?.active_mode === 'carrier') && (
        <section>
          <h2 className="font-display font-semibold text-lg text-navy mb-3">{t('dashboard.iSend')}</h2>
          <div className="bg-white rounded-card border border-navy/10 p-6 text-center">
            <p className="text-sm font-body text-muted mb-4">
              {t('dashboard.findCarrier')}
            </p>
            <Link
              to="/trips"
              className="inline-block bg-amber text-white font-display font-medium px-5 py-2.5 rounded-field text-sm hover:opacity-90 transition-opacity"
            >
              {t('dashboard.findTrip')}
            </Link>
          </div>
        </section>
      )}

      <div className="flex justify-end pt-4">
        <MonoText className="text-xs text-muted">v{APP_VERSION}</MonoText>
      </div>
    </div>
  )
}
