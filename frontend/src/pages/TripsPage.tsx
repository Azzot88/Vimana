import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useEffect, useId, useRef, useState } from 'react'
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
import TripPreview from '../components/TripPreview'
import UBAChip from '../components/UBAChip'
import { filterNotesForCorridor, useRouteNotes } from '../hooks/useRouteNotes'
import { routeChain } from '../lib/format'
import { usePersistedState } from '../hooks/usePersistedState'
import { usePrefs } from '../hooks/usePrefs'

/** T3.11.07 — the landing at the end of the route, or null.
 *
 *  Read off the last leg rather than off the trip: the arrival belongs to a
 *  flight, and a trip has no column for it — `Trip.depart_at` is denormalised
 *  because search and the countdown stand on it, and nothing stands on the
 *  landing. Null for every trip published before 2026-09-06 and for every
 *  carrier who did not state one, which is most of them.
 *
 *  Called by: the route card below.
 */
function arrivalOf(trip: Trip): string | null {
  const last = trip.legs?.[trip.legs.length - 1]
  return last?.arrive_at ?? null
}

export default function TripsPage() {
  // T_TEST.8 — the search row had three visible labels and none of them was
  // attached to anything. axe only reported the date, because its `label` rule
  // accepts a non-empty placeholder as a last resort and the two airport fields
  // have one. A placeholder is not a name: it disappears the moment you type.
  const originId = useId()
  const destId = useId()
  const dateId = useId()
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
  const [error, setError] = useState('')
  /* T3.11.07 — the trip that was just published (owner's request 2026-09-06).
     Publishing used to drop the carrier on the board with no way to tell which
     of the cards was the one they had just written — on a busy corridor it is
     not even the first. The id travels in the query string rather than in
     router state so the page survives a reload and the link can be shared with
     nobody in particular. */
  const [params, setParams] = useSearchParams()
  const justPublished = params.get('trip')
  /* T3.11.07 — the trip whose detail panel is open (owner's request
     2026-09-06). The board card is a summary and stays one; the panel holds
     the rest. Held as the object rather than an id: the list already has it,
     and a second fetch for something on screen is a spinner for nothing. */
  const [previewTrip, setPreviewTrip] = useState<Trip | null>(null)
  /* Opened once, not every render: closing the panel must not reopen it, and
     the list refetches. */
  const openedForPublish = useRef(false)
  const navigate = useNavigate()

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

  /* T3.11.07 — a freshly published trip opens its own detail (owner's request
     2026-09-06). That is what «посмотреть свой рейс после публикации» asks
     for: the carrier lands on what they wrote, not on a list they have to
     search for it in. The ring on the card stays, so closing the panel leaves
     the trip still findable. */
  useEffect(() => {
    if (!justPublished || openedForPublish.current) return
    const published = trips.find((x) => x.id === justPublished)
    if (!published) return
    openedForPublish.current = true
    setPreviewTrip(published)
  }, [justPublished, trips])

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
      const { data: deal } = await matchDeal({
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
      setOrderTripId(null)
      /* T3.11.23 — one press, and you are inside the deal (owner's model
         2026-09-07): the server opens the chat with this carrier and nests the
         deal in it, and the person lands in the deal. They see a deal; they are
         in fact in a chat that has one open. A success banner on the board
         instead would have left the conversation somewhere they have to go
         looking for — and it was already unclear where. */
      navigate(`/deals/${deal.id}/vault`)
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
          <label htmlFor={originId} className="block text-xs font-body font-medium text-navy/60 mb-1">{t('trips.from')}</label>
          <AirportSelect value={origin} onChange={setOrigin} placeholder="DXB" inputId={originId} />
        </div>
        <div className="md:flex-1 md:min-w-[160px]">
          <label htmlFor={destId} className="block text-xs font-body font-medium text-navy/60 mb-1">{t('trips.to')}</label>
          <AirportSelect value={destination} onChange={setDestination} placeholder="JFK" inputId={destId} />
        </div>
        <div className="md:flex-1 md:min-w-[140px]">
          <label htmlFor={dateId} className="block text-xs font-body font-medium text-navy/60 mb-1">{t('trips.date')}</label>
          <input
            id={dateId}
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

      {/* T3.11.07 — «посмотреть свой рейс после публикации» (owner's request
          2026-09-06). The form used to hand the carrier the board and nothing
          else: the trip was there, in a list of other people's, with no way to
          tell which one had just been written. Dismissing drops the query
          parameter rather than hiding a banner, so a reload does not bring it
          back and the ring goes with it. */}
      {justPublished && (
        <div className="bg-cyan/5 border border-cyan/30 rounded-card p-4 flex items-center justify-between gap-3">
          <p className="text-sm font-body text-navy">{t('trips.published')}</p>
          <button
            type="button"
            onClick={() => {
              const next = new URLSearchParams(params)
              next.delete('trip')
              setParams(next, { replace: true })
            }}
            className="text-xs font-body text-navy/50 hover:text-navy shrink-0"
          >
            {t('common.close')}
          </button>
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
            <div
              key={trip.id}
              /* T3.11.07 — the card the carrier just published, scrolled to and
                 ringed. `ref` rather than an effect keyed on the list: the node
                 exists exactly once, when it renders, and waiting for a second
                 render to find it by id is how this ends up scrolling to the
                 wrong card on a slow fetch. */
              ref={
                trip.id === justPublished
                  ? (node) =>
                      node?.scrollIntoView({ behavior: 'smooth', block: 'center' })
                  : undefined
              }
              className={`bg-white rounded-card border p-4 sm:p-5 ${
                trip.id === justPublished
                  ? 'border-cyan ring-2 ring-cyan/30'
                  : 'border-navy/10'
              }`}
            >
              <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
                <div className="space-y-2">
                  <MonoText className="text-base text-navy font-medium">
                    {routeChain(trip)}
                  </MonoText>
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs font-body text-navy/50">
                    <span className="inline-flex items-center gap-1.5 flex-wrap">
                      {t('trips.carrier')}:{' '}
                      {/* T_UX.18 — handing a stranger a parcel is the moment
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
                    {/* T3.11.07 — the landing at the end of the route, when the
                        carrier stated one. It is the time the sender actually
                        plans around: departure says when the parcel has to be
                        handed over, arrival says when it can be collected. Only
                        shown when it exists — most trips have none, and an
                        invented one would be worse than a missing one. */}
                    {arrivalOf(trip) && (
                      <span>
                        {t('trips.arrival')}:{' '}
                        <MonoText className="text-xs">
                          {prefs.dateTime(arrivalOf(trip))}
                        </MonoText>
                      </span>
                    )}
                    {/* T3.11.07 — a trip with no stated weight says nothing
                        about weight, and the qualitative size is what most
                        carriers actually answer. Neither is invented. */}
                    {trip.capacity !== null && (
                      <span>{t('trips.capacity')}: <MonoText className="text-xs">{prefs.weight(trip.capacity)}</MonoText></span>
                    )}
                    {trip.size_hint && (
                      <span>{t(`trips.sizeHint.${trip.size_hint}`)}</span>
                    )}
                    {/* T3.11.07 — a refusal the sender has to read before
                        writing, not after. Amber rather than red: it is a
                        boundary, not an error. */}
                    {trip.excluded && trip.excluded.length > 0 && (
                      <span className="text-amber">
                        {t('trips.excludedPrefix')}{' '}
                        {trip.excluded
                          .map((x) => t(`trips.excluded.${x}`))
                          .join(', ')}
                      </span>
                    )}
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
                <div className="flex flex-col sm:flex-row gap-2 shrink-0 w-full sm:w-auto sm:ml-4">
                  {/* T3.11.07 — the card stays a summary; everything else is one
                      click away (owner's request 2026-09-06). Shown to everyone,
                      not only the owner: a sender deciding whether to write has
                      the same questions — where the handover happens, what is
                      refused, how settlement works — and the card has room for
                      none of them. */}
                  <button
                    type="button"
                    onClick={() => setPreviewTrip(trip)}
                    className="border border-navy/20 text-navy/70 font-body px-4 py-3 min-h-[2.75rem] rounded-field text-sm hover:bg-ivory transition-colors"
                  >
                    {t('trips.preview.open')}
                  </button>
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
                      onClick={() => setOrderTripId(trip.id)}
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

      {previewTrip && (
        <TripPreview
          trip={previewTrip}
          onClose={() => setPreviewTrip(null)}
          /* T3.11.07 — editing is offered only to the owner, and only while the
             trip is still a listing. A matched or cancelled trip is part of what
             two people agreed to; the server refuses it either way, and a button
             that exists to be refused is worse than one that is not there. The
             trip travels in router state so the wizard opens without a second
             request for something already on screen. */
          onEdit={
            previewTrip.carrier_id === user?.id && previewTrip.status === 'open'
              ? () =>
                  navigate(`/trips/new?edit=${previewTrip.id}`, {
                    state: { trip: previewTrip },
                  })
              : undefined
          }
          /* T3.11.07 — «Обратный рейс» (owner's request 2026-09-06). Owner-only
             like editing, but offered whatever the status: the way back is
             planned long after the outbound has been matched, and often
             precisely because it has. */
          onReverse={
            previewTrip.carrier_id === user?.id
              ? () =>
                  navigate(`/trips/new?reverse=${previewTrip.id}`, {
                    state: { trip: previewTrip },
                  })
              : undefined
          }
          /* T3.11.16 — «повторить»: the same route, dates cleared. It reuses
             the reverse machinery minus the reversal, because «this route
             again» and «this route back» are the same form pre-filled from the
             same trip. */
          onRepeat={
            previewTrip.carrier_id === user?.id
              ? () =>
                  navigate(`/trips/new?repeat=${previewTrip.id}`, {
                    state: { trip: previewTrip },
                  })
              : undefined
          }
        />
      )}
    </div>
  )
}
