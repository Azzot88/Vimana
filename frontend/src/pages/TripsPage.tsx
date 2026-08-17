import { Link } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../stores/auth'
import { listTrips, type Trip } from '../api/trips'
import { matchDeal } from '../api/deals'
import AirportSelect from '../components/AirportSelect'
import CategorySelect from '../components/CategorySelect'
import InquiryPanel from '../components/InquiryPanel'
import MonoText from '../components/MonoText'
import NostrBadge from '../components/NostrBadge'
import RouteNoteBadge from '../components/RouteNoteBadge'
import UBAChip from '../components/UBAChip'
import { filterNotesForCorridor, useRouteNotes } from '../hooks/useRouteNotes'
import { usePersistedState } from '../hooks/usePersistedState'
import { usePrefs } from '../hooks/usePrefs'

export default function TripsPage() {
  const prefs = usePrefs()
  const user = useAuthStore((s) => s.user)
  const { t } = useTranslation()
  const [trips, setTrips] = useState<Trip[]>([])
  const [loading, setLoading] = useState(true)
  // T_UX.2 pt.3 — все active route notes одним запросом, фильтр per trip
  // в JSX ниже. Меньше XHR чем per-card fetch.
  const { notes: allNotes } = useRouteNotes(undefined, undefined)
  const [origin, setOrigin] = usePersistedState<string>('trips:filter:origin', '')
  const [destination, setDestination] = usePersistedState<string>('trips:filter:destination', '')
  const [date, setDate] = usePersistedState<string>('trips:filter:date', '')
  const [orderTripId, setOrderTripId] = useState<string | null>(null)
  const [chatTrip, setChatTrip] = useState<{ id: string; carrierName: string } | null>(null)
  const [cargoDesc, setCargoDesc] = useState('')
  const [cargoCategory, setCargoCategory] = useState('other')
  const [declaredValue, setDeclaredValue] = useState('')
  const [recipientContact, setRecipientContact] = useState('')
  const [orderLoading, setOrderLoading] = useState(false)
  const [orderSuccess, setOrderSuccess] = useState(false)
  const [error, setError] = useState('')

  const fetchTrips = async () => {
    setLoading(true)
    try {
      const { data } = await listTrips({
        origin: origin || undefined,
        destination: destination || undefined,
        date: date || undefined,
      })
      setTrips(data.items)
    } catch {
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchTrips()
  }, [])

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    fetchTrips()
  }

  const handleOrder = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!orderTripId) return
    setOrderLoading(true)
    setError('')
    const trip = trips.find((t) => t.id === orderTripId)
    if (!trip) return
    try {
      await matchDeal({
        trip_id: orderTripId,
        order: {
          recipient_contact: recipientContact,
          origin: trip.origin,
          destination: trip.destination,
          category: cargoCategory,
          declared_value: Number(declaredValue),
          description: cargoDesc,
        },
      })
      setOrderSuccess(true)
      setOrderTripId(null)
    } catch {
      setError(t('trips.requestError'))
    } finally {
      setOrderLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="font-display font-bold text-2xl text-navy">{t('trips.title')}</h1>

      <form onSubmit={handleSearch} className="bg-white rounded-card border border-navy/10 p-4 grid grid-cols-1 sm:grid-cols-2 md:flex md:flex-wrap gap-3 md:items-end">
        <div className="md:flex-1 md:min-w-[160px]">
          <label className="block text-xs font-body font-medium text-navy/60 mb-1">{t('trips.from')}</label>
          <AirportSelect value={origin} onChange={setOrigin} placeholder="DXB" />
        </div>
        <div className="md:flex-1 md:min-w-[160px]">
          <label className="block text-xs font-body font-medium text-navy/60 mb-1">{t('trips.to')}</label>
          <AirportSelect value={destination} onChange={setDestination} placeholder="JFK" />
        </div>
        <div className="md:flex-1 md:min-w-[140px]">
          <label className="block text-xs font-body font-medium text-navy/60 mb-1">{t('trips.date')}</label>
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="w-full border border-navy/20 rounded-field px-3 py-2 min-h-[2.75rem] text-sm font-mono text-navy focus:outline-none focus:border-cyan transition-colors"
          />
        </div>
        <button
          type="submit"
          className="sm:col-span-2 md:col-span-1 bg-navy text-ivory font-display font-medium px-5 py-3 min-h-[2.75rem] rounded-field text-sm hover:bg-navy-mid transition-colors"
        >
          {t('trips.search')}
        </button>
      </form>

      {orderSuccess && (
        <div className="bg-success/5 border border-success/30 rounded-card p-4">
          <p className="text-sm font-body text-success">{t('trips.requestSent')}</p>
        </div>
      )}

      {loading ? (
        <div className="text-center py-12">
          <MonoText className="text-navy/40 text-sm">{t('common.loading')}</MonoText>
        </div>
      ) : trips.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-sm font-body text-navy/40">{t('trips.noTrips')}</p>
        </div>
      ) : (
        <div className="grid gap-4">
          {trips.map((trip) => (
            <div key={trip.id} className="bg-white rounded-card border border-navy/10 p-4 sm:p-5">
              <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
                <div className="space-y-2">
                  <MonoText className="text-base text-navy font-medium">
                    {trip.origin} → {trip.destination}
                  </MonoText>
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs font-body text-navy/50">
                    <span className="inline-flex items-center gap-1.5 flex-wrap">
                      {t('trips.carrier')}:{' '}
                      {/* T_UX.14 — handing a stranger a parcel is the moment
                          somebody most wants to know who they are dealing with.
                          The name stops being text. */}
                      <Link
                        to={`/carriers/${trip.carrier_id}`}
                        onClick={(e) => e.stopPropagation()}
                        className="text-navy font-medium hover:text-cyan transition-colors underline decoration-navy/20 underline-offset-2"
                      >
                        {trip.carrier_name}
                      </Link>
                      <UBAChip uba={trip.carrier_uba} level={trip.carrier_uba_level} />
                      {/* T3.17 — a retired identity, said before anyone offers
                          it a deal. Grey, not red: this is not a warning about
                          the person, it is a fact about what the account can
                          still do. */}
                      {trip.carrier_key_lost && (
                        <span
                          data-testid="carrier-key-lost"
                          title={t('trips.keyLostHint') as string}
                          className="text-xs font-body px-2 py-0.5 rounded bg-navy/10 text-navy/50"
                        >
                          {t('trips.keyLost')}
                        </span>
                      )}
                      <NostrBadge eventId={trip.nostr_event_id} publishedAt={trip.nostr_published_at} />
                      {filterNotesForCorridor(allNotes, trip.origin, trip.destination).map((n) => (
                        <RouteNoteBadge key={n.id} note={n} compact />
                      ))}
                    </span>
                    <MonoText className="text-xs">{prefs.dateTime(trip.depart_at)}</MonoText>
                    <span>{t('trips.capacity')}: <MonoText className="text-xs">{prefs.weight(trip.capacity)}</MonoText></span>
                    {/* T3.35 — the published baseline, so two trips on one
                        corridor are comparable before anyone opens a chat.
                        Absent price is stated as such rather than hidden. */}
                    {trip.carriage_rules && (
                      <span
                        title={trip.carriage_rules}
                        className="inline-flex items-center gap-1 text-navy/50"
                      >
                        📋 {t('trips.hasRules')}
                      </span>
                    )}
                    <span>
                      {t('trips.pricePerKg')}:{' '}
                      <MonoText className="text-xs">
                        {trip.price_per_kg
                          ? `${trip.price_per_kg} ${trip.currency ?? 'USD'}`
                          : t('trips.priceOnRequest')}
                      </MonoText>
                    </span>
                  </div>
                  {trip.allowed_categories.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {trip.allowed_categories.map((cat) => (
                        <span key={cat} className="text-xs font-mono bg-ivory px-2 py-0.5 rounded text-navy/60">
                          {cat}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                {user?.active_mode !== 'carrier' && trip.carrier_id !== user?.id && (
                  <div className="flex flex-col sm:flex-row gap-2 shrink-0 w-full sm:w-auto sm:ml-4">
                    <button
                      onClick={() => setChatTrip({ id: trip.id, carrierName: trip.carrier_name })}
                      className="border border-navy/20 text-navy font-display font-medium px-4 py-3 min-h-[2.75rem] rounded-field text-sm hover:bg-ivory transition-colors"
                      aria-label={t('inquiry.chatWith', { name: trip.carrier_name }) as string}
                    >
                      {t('inquiry.chatButton')}
                    </button>
                    <button
                      onClick={() => { setOrderTripId(trip.id); setOrderSuccess(false) }}
                      className="bg-amber text-white font-display font-medium px-4 py-3 min-h-[2.75rem] rounded-field text-sm hover:opacity-90 transition-opacity"
                    >
                      {t('trips.sendPackage')}
                    </button>
                  </div>
                )}
              </div>

              {orderTripId === trip.id && (
                <form onSubmit={handleOrder} className="mt-4 pt-4 border-t border-navy/10 space-y-3">
                  <p className="text-xs font-display font-semibold text-navy/60 uppercase tracking-wide">{t('trips.requestTitle')}</p>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div className="col-span-2">
                      <label className="block text-xs font-body font-medium text-navy/60 mb-1">{t('trips.recipientContact')}</label>
                      <input
                        type="text"
                        value={recipientContact}
                        onChange={(e) => setRecipientContact(e.target.value)}
                        required
                        className="w-full border border-navy/20 rounded-field px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan"
                      />
                    </div>
                    <div className="col-span-2">
                      <label className="block text-xs font-body font-medium text-navy/60 mb-1">{t('trips.cargoDescription')}</label>
                      <input
                        type="text"
                        value={cargoDesc}
                        onChange={(e) => setCargoDesc(e.target.value)}
                        className="w-full border border-navy/20 rounded-field px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-body font-medium text-navy/60 mb-1">{t('trips.declaredValue')}</label>
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        value={declaredValue}
                        onChange={(e) => setDeclaredValue(e.target.value)}
                        required
                        className="w-full border border-navy/20 rounded-field px-3 py-2 text-sm font-mono text-navy focus:outline-none focus:border-cyan"
                        placeholder="100"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-body font-medium text-navy/60 mb-1">{t('trips.category')}</label>
                      <CategorySelect value={cargoCategory} onChange={setCargoCategory} />
                    </div>
                  </div>
                  {error && <p className="text-xs font-mono text-amber">{error}</p>}
                  <div className="flex gap-2">
                    <button
                      type="submit"
                      disabled={orderLoading}
                      className="bg-navy text-ivory font-display font-medium px-4 py-2 rounded-field text-sm hover:bg-navy-mid transition-colors disabled:opacity-50"
                    >
                      {orderLoading ? t('trips.submitting') : t('trips.submit')}
                    </button>
                    <button
                      type="button"
                      onClick={() => setOrderTripId(null)}
                      className="text-sm font-body text-navy/50 hover:text-navy transition-colors px-3"
                    >
                      {t('common.cancel')}
                    </button>
                  </div>
                </form>
              )}
            </div>
          ))}
        </div>
      )}

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
