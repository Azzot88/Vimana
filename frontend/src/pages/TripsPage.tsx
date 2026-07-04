import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../stores/auth'
import { listTrips, type Trip } from '../api/trips'
import { matchDeal } from '../api/deals'
import AirportSelect from '../components/AirportSelect'
import MonoText from '../components/MonoText'

const CATEGORIES = ['documents', 'electronics', 'clothing', 'food', 'cosmetics', 'other']

export default function TripsPage() {
  const user = useAuthStore((s) => s.user)
  const { t, i18n } = useTranslation()
  const [trips, setTrips] = useState<Trip[]>([])
  const [loading, setLoading] = useState(true)
  const [origin, setOrigin] = useState('')
  const [destination, setDestination] = useState('')
  const [date, setDate] = useState('')
  const [orderTripId, setOrderTripId] = useState<string | null>(null)
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
      setTrips(data)
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

      <form onSubmit={handleSearch} className="bg-white rounded-xl border border-navy/10 p-4 flex flex-wrap gap-3 items-end">
        <div className="flex-1 min-w-[160px]">
          <label className="block text-xs font-body font-medium text-navy/60 mb-1">{t('trips.from')}</label>
          <AirportSelect value={origin} onChange={setOrigin} placeholder="DXB" />
        </div>
        <div className="flex-1 min-w-[160px]">
          <label className="block text-xs font-body font-medium text-navy/60 mb-1">{t('trips.to')}</label>
          <AirportSelect value={destination} onChange={setDestination} placeholder="JFK" />
        </div>
        <div className="flex-1 min-w-[140px]">
          <label className="block text-xs font-body font-medium text-navy/60 mb-1">{t('trips.date')}</label>
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="w-full border border-navy/20 rounded-lg px-3 py-2 text-sm font-mono text-navy focus:outline-none focus:border-cyan transition-colors"
          />
        </div>
        <button
          type="submit"
          className="bg-navy text-ivory font-display font-medium px-5 py-2 rounded-lg text-sm hover:bg-navy-mid transition-colors"
        >
          {t('trips.search')}
        </button>
      </form>

      {orderSuccess && (
        <div className="bg-green-50 border border-green-200 rounded-xl p-4">
          <p className="text-sm font-body text-green-700">{t('trips.requestSent')}</p>
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
            <div key={trip.id} className="bg-white rounded-xl border border-navy/10 p-5">
              <div className="flex items-start justify-between">
                <div className="space-y-2">
                  <MonoText className="text-base text-navy font-medium">
                    {trip.origin} → {trip.destination}
                  </MonoText>
                  <div className="flex items-center gap-4 text-xs font-body text-navy/50">
                    <span>{t('trips.carrier')}: <span className="text-navy font-medium">{trip.carrier_name}</span></span>
                    <MonoText className="text-xs">{new Date(trip.depart_at).toLocaleString(i18n.language)}</MonoText>
                    <span>{t('trips.capacity')}: <MonoText className="text-xs">{trip.capacity} кг</MonoText></span>
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
                {!user?.is_carrier && trip.carrier_id !== user?.id && (
                  <button
                    onClick={() => { setOrderTripId(trip.id); setOrderSuccess(false) }}
                    className="bg-amber text-white font-display font-medium px-4 py-2 rounded-lg text-sm hover:opacity-90 transition-opacity shrink-0 ml-4"
                  >
                    {t('trips.sendPackage')}
                  </button>
                )}
              </div>

              {orderTripId === trip.id && (
                <form onSubmit={handleOrder} className="mt-4 pt-4 border-t border-navy/10 space-y-3">
                  <p className="text-xs font-display font-semibold text-navy/60 uppercase tracking-wide">{t('trips.requestTitle')}</p>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="col-span-2">
                      <label className="block text-xs font-body font-medium text-navy/60 mb-1">{t('trips.recipientContact')}</label>
                      <input
                        type="text"
                        value={recipientContact}
                        onChange={(e) => setRecipientContact(e.target.value)}
                        required
                        className="w-full border border-navy/20 rounded-lg px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan"
                      />
                    </div>
                    <div className="col-span-2">
                      <label className="block text-xs font-body font-medium text-navy/60 mb-1">{t('trips.cargoDescription')}</label>
                      <input
                        type="text"
                        value={cargoDesc}
                        onChange={(e) => setCargoDesc(e.target.value)}
                        className="w-full border border-navy/20 rounded-lg px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan"
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
                        className="w-full border border-navy/20 rounded-lg px-3 py-2 text-sm font-mono text-navy focus:outline-none focus:border-cyan"
                        placeholder="100"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-body font-medium text-navy/60 mb-1">{t('trips.category')}</label>
                      <select
                        value={cargoCategory}
                        onChange={(e) => setCargoCategory(e.target.value)}
                        className="w-full border border-navy/20 rounded-lg px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan"
                      >
                        {CATEGORIES.map((c) => (
                          <option key={c} value={c}>{c}</option>
                        ))}
                      </select>
                    </div>
                  </div>
                  {error && <p className="text-xs font-mono text-orange-600">{error}</p>}
                  <div className="flex gap-2">
                    <button
                      type="submit"
                      disabled={orderLoading}
                      className="bg-navy text-ivory font-display font-medium px-4 py-2 rounded-lg text-sm hover:bg-navy-mid transition-colors disabled:opacity-50"
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
    </div>
  )
}
