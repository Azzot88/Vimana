import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import type { HandoverSide, Trip } from '../api/trips'
import { routeNode } from '../lib/format'
import { usePrefs } from '../hooks/usePrefs'
import MonoText from './MonoText'
import NostrBadge from './NostrBadge'

/** T3.11.07 — the whole trip, in a panel over the board (owner's request
 *  2026-09-06).
 *
 *  The board card is a summary and has to stay one: it is read while scanning a
 *  list. But the trip holds four times what the card shows — the chain with its
 *  hours, both ends of the handover, the exclusions, the settlement, the
 *  carriage rules — and a carrier who has just published wants to see that it
 *  all landed. So the detail opens over the board rather than on a page of its
 *  own: no navigation, no losing the list, and the "did that save" question is
 *  answered in one click.
 *
 *  **Nothing is invented here.** A field the carrier did not answer is left out
 *  rather than printed as a dash or a default — the whole point of the trip
 *  model is that "did not say" and "said none" are different answers, and a
 *  panel that renders both as `—` throws that away where it matters most.
 *
 *  Editing is a separate button and only the owner sees it: it hands the trip
 *  back to the wizard, which updates the same row rather than publishing a new
 *  one.
 *
 *  Called by: `pages/TripsPage`.
 */
interface Props {
  trip: Trip
  /** Shown only when the viewer owns this trip and it is still open. */
  onEdit?: () => void
  /** T3.11.07 — start a new trip flown the other way. Owner-only, but unlike
   *  editing it is offered whatever the status: a carrier can be planning the
   *  way back long after the outbound has been matched or even flown. */
  onReverse?: () => void
  /** T3.11.16 — «повторить»: the same route on a new date. A different
   *  intention from bumping and different in the data too — repeating a route
   *  is 5.4 % of the market («летаю регулярно»), holding a listing at the top
   *  is 60.8 %. One button for both would record one as the other. */
  onRepeat?: () => void
  /** T3.11.16 — «поднять». Owner-only and only while the trip is a listing;
   *  the caller decides, because it is the caller that knows the quota answer
   *  and has somewhere to show it. */
  onBump?: () => void
  bumpNote?: string
  onClose: () => void
}

export default function TripPreview({
  trip,
  onEdit,
  onReverse,
  onRepeat,
  onBump,
  bumpNote,
  onClose,
}: Props) {
  const { t } = useTranslation()
  const prefs = usePrefs()

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    // The board behind keeps its scroll position rather than scrolling under
    // the panel — the carrier came from a place in the list and goes back to it.
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = previous
    }
  }, [onClose])

  const legs = trip.legs ?? []
  const allowance = trip.max_declared_value
  const allowanceCurrency = trip.max_declared_value_currency || trip.currency

  /** A block with a heading, rendered only when it has something to say. */
  const section = (title: React.ReactNode, body: React.ReactNode) => (
    <section className="border-t border-navy/10 pt-3 space-y-1.5">
      <h3 className="text-[11px] font-display font-semibold text-navy/45 uppercase tracking-wide">
        {title}
      </h3>
      {body}
    </section>
  )

  const chips = (values: string[], label: (v: string) => React.ReactNode) => (
    <div className="flex flex-wrap gap-1.5">
      {values.map((v) => (
        <span
          key={v}
          className="text-xs font-body bg-navy/[0.04] border border-navy/10 px-2 py-1 rounded-full text-navy/70"
        >
          {label(v)}
        </span>
      ))}
    </div>
  )

  /** One end of the handover. Rendered only if the carrier said anything about
   *  it: an empty block would read as "nothing is possible here", and what the
   *  model means is "they did not say". */
  const handover = (
    side: HandoverSide | null | undefined,
    heading: React.ReactNode,
  ) => {
    if (!side) return null
    const anything =
      side.methods.length > 0 ||
      side.points.length > 0 ||
      (side.postal_services?.length ?? 0) > 0 ||
      side.address_id ||
      side.meeting_place_id
    if (!anything) return null
    return section(
      heading,
      <div className="space-y-1.5">
        {side.methods.length > 0 && chips(side.methods, (m) => t(`cards.opt.${m}`))}
        {side.points.length > 0 && (
          <p className="text-xs font-body text-navy/70">{side.points.join(' · ')}</p>
        )}
        {(side.postal_services?.length ?? 0) > 0 &&
          chips(side.postal_services ?? [], (s) => s)}
        {/* The id itself is never printed: it says nothing to a reader and the
            row behind it is the carrier's private address. That one is attached
            is worth saying, because it is what a sender will be handed. */}
        {side.address_id && (
          <p className="text-[11px] font-body text-navy/45">
            {t('trips.preview.hasAddress')}
          </p>
        )}
        {side.meeting_place_id && (
          <p className="text-[11px] font-body text-navy/45">
            {t('trips.preview.hasMeetingPlace')}
          </p>
        )}
      </div>,
    )
  }

  return (
    <div
      className="fixed inset-0 z-modal bg-navy/50 flex items-end sm:items-center justify-center sm:p-4"
      role="dialog"
      aria-modal="true"
      aria-label={t('trips.preview.title') as string}
      onClick={onClose}
    >
      <div
        /* Stops a click inside the panel from reaching the backdrop. Without
           it, selecting text in the carriage rules closes the thing you are
           reading. */
        onClick={(e) => e.stopPropagation()}
        className="bg-white w-full sm:max-w-2xl max-h-[90dvh] sm:rounded-card rounded-t-card border border-navy/10 shadow-lift flex flex-col"
      >
        <header className="flex items-start justify-between gap-3 p-5 pb-3">
          <div className="min-w-0 space-y-1">
            <MonoText className="block text-lg text-navy font-medium">
              {legs.length > 0
                ? [
                    routeNode(legs[0].origin, legs[0].origin_city),
                    ...legs.map((l) => routeNode(l.destination, l.destination_city)),
                  ].join(' → ')
                : `${trip.origin} → ${trip.destination}`}
            </MonoText>
            <p className="text-xs font-body text-navy/50">
              {t('trips.carrier')}: {trip.carrier_name}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t('common.close') as string}
            className="shrink-0 w-8 h-8 rounded-full text-navy/40 hover:text-navy hover:bg-navy/5 text-xl leading-none"
          >
            ×
          </button>
        </header>

        <div className="overflow-y-auto px-5 pb-5 space-y-3">
          {section(
            t('trips.newTripCell.route'),
            <ol className="space-y-1.5">
              {legs.map((leg) => (
                <li key={leg.order} className="text-xs font-body text-navy/70">
                  <MonoText className="text-xs text-navy">
                    {routeNode(leg.origin, leg.origin_city)} →{' '}
                    {routeNode(leg.destination, leg.destination_city)}
                  </MonoText>
                  <span className="block text-navy/50 mt-0.5">
                    {prefs.dateTime(leg.depart_at)}
                    {/* Only the end of the route carries one, so this shows on
                        a single row of the chain. */}
                    {leg.arrive_at && ` → ${prefs.dateTime(leg.arrive_at)}`}
                  </span>
                </li>
              ))}
              {legs.length > 0 && (
                <li className="text-[11px] font-body text-navy/45">
                  {t(`trips.flownBy.${legs[0].flown_by}`)}
                </li>
              )}
            </ol>,
          )}

          {(trip.capacity !== null || trip.size_hint || trip.space_kind) &&
            section(
              t('trips.newTripCell.capacity'),
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs font-body text-navy/70">
                {/* Null weight is not zero weight: 97.6 % of this market never
                    states kilograms, and the qualitative size is what they
                    answer instead. Neither is filled in for them. */}
                {trip.capacity !== null && trip.capacity !== undefined && (
                  <MonoText className="text-xs text-navy">
                    {prefs.weight(trip.capacity)}
                  </MonoText>
                )}
                {trip.size_hint && <span>{t(`trips.sizeHint.${trip.size_hint}`)}</span>}
                {trip.space_kind && trip.space_kind !== 'unspecified' && (
                  <span>{t(`trips.spaceKind.${trip.space_kind}`)}</span>
                )}
              </div>,
            )}

          {(trip.allowed_categories?.length ?? 0) > 0 &&
            section(
              t('trips.newTripCell.categories'),
              chips(trip.allowed_categories ?? [], (c) =>
                t(`categories.${c}`, { defaultValue: c }),
              ),
            )}

          {(trip.excluded?.length ?? 0) > 0 &&
            section(
              t('trips.excludedPrefix'),
              chips(trip.excluded ?? [], (e) => t(`trips.excluded.${e}`)),
            )}

          {allowance !== null && allowance !== undefined &&
            section(
              t('trips.maxDeclaredValue'),
              <MonoText className="text-sm text-navy">
                {allowance} {allowanceCurrency}
              </MonoText>,
            )}

          {handover(
            trip.handover_origin,
            `${t('trips.handoverOrigin')} ${trip.origin}`,
          )}
          {handover(
            trip.handover_destination,
            `${t('trips.handoverDestination')} ${trip.destination}`,
          )}

          {(trip.services?.length ?? 0) > 0 &&
            section(
              t('trips.newTripCell.services'),
              chips(trip.services ?? [], (s) => t(`trips.services.${s}`)),
            )}

          {(trip.payment_model ||
            (trip.payment_systems?.length ?? 0) > 0 ||
            trip.price_per_kg != null ||
            trip.min_deal_price != null) &&
            section(
              t('trips.newTripCell.payment'),
              <div className="space-y-1.5">
                {trip.payment_model && (
                  <p className="text-xs font-body text-navy/70">
                    {t(`trips.paymentModel.${trip.payment_model}`)}
                  </p>
                )}
                {(trip.payment_systems?.length ?? 0) > 0 &&
                  chips(trip.payment_systems ?? [], (s) => s)}
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs font-body text-navy/70">
                  {/* No price is "price on request", which 99.9 % of this market
                      publishes — not a price of zero. */}
                  {trip.price_per_kg != null && (
                    <span>
                      {t('trips.pricePerKg')}:{' '}
                      <MonoText className="text-xs text-navy">
                        {trip.price_per_kg} {trip.currency}
                      </MonoText>
                    </span>
                  )}
                  {trip.min_deal_price != null && (
                    <span>
                      {t('trips.minDealPrice')}:{' '}
                      <MonoText className="text-xs text-navy">
                        {trip.min_deal_price} {trip.currency}
                      </MonoText>
                    </span>
                  )}
                </div>
              </div>,
            )}

          {trip.carriage_rules &&
            section(
              t('trips.newTripCell.rules'),
              <p className="text-xs font-body text-navy/70 whitespace-pre-wrap">
                {trip.carriage_rules}
              </p>,
            )}

          <div className="border-t border-navy/10 pt-3 flex items-center gap-3">
            <NostrBadge
              eventId={trip.nostr_event_id}
              publishedAt={trip.nostr_published_at}
            />
            <span className="text-[11px] font-body text-navy/40">
              {t('trips.preview.publishedAt')}: {prefs.dateTime(trip.created_at)}
            </span>
          </div>
        </div>

        {/* T3.11.07 — editing behind its own button (owner's wording
            2026-09-06). It hands the trip back to the wizard, which updates the
            same row: the id is what every inquiry and deal points at, so a
            carrier fixing a departure hour must not end up with a second
            listing and an orphaned conversation. */}
        {(onEdit || onReverse || onRepeat || onBump) && (
          <footer className="border-t border-navy/10 p-4 flex flex-wrap items-center justify-end gap-2 bg-white sm:rounded-b-card">
            {/* The quota answer, in the one place the press happened. A 429 is
                not an error to hide: the carrier may do this, just not again
                yet, and they need to know which. */}
            {bumpNote && (
              <span className="mr-auto text-[11px] font-body text-navy/50">
                {bumpNote}
              </span>
            )}
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 min-h-[2.75rem] rounded-field text-sm font-body text-navy/60"
            >
              {t('common.close')}
            </button>
            {/* T3.11.16 — «поднять» and «повторить» sit side by side because
                they are near-neighbours in intent and opposite in effect: one
                keeps this listing and moves it up, the other starts a new one
                on the same route. Naming both is what stops the second being
                used as the first, which on this market is the default habit. */}
            {onBump && (
              <button
                type="button"
                onClick={onBump}
                title={t('trips.preview.bumpHint') as string}
                className="px-4 py-2 min-h-[2.75rem] rounded-field border border-amber/50 text-amber text-sm font-display font-medium hover:bg-amber/5 transition-colors"
              >
                {t('trips.preview.bump')}
              </button>
            )}
            {onRepeat && (
              <button
                type="button"
                onClick={onRepeat}
                title={t('trips.preview.repeatHint') as string}
                className="px-4 py-2 min-h-[2.75rem] rounded-field border border-navy/20 text-navy/70 text-sm font-display font-medium hover:border-navy/40 transition-colors"
              >
                {t('trips.preview.repeat')}
              </button>
            )}
            {/* T3.11.07 — «Обратный рейс». A carrier who flies out almost always
                comes back, and the return listing is this one with the route
                reversed and the dates unknown; today that half of the market is
                published as a line in a chat because the form asks for all
                twenty answers again. */}
            {onReverse && (
              <button
                type="button"
                onClick={onReverse}
                title={t('trips.preview.reverseHint') as string}
                className="px-4 py-2 min-h-[2.75rem] rounded-field border border-cyan/50 text-cyan text-sm font-display font-medium hover:bg-cyan/5 transition-colors"
              >
                {t('trips.preview.reverse')}
              </button>
            )}
            {/* Its own guard now that the footer can be here for the return
                button alone: editing is refused on a trip that is no longer a
                listing, and a button that exists to be refused is worse than
                one that is not there. */}
            {onEdit && (
              <button
                type="button"
                onClick={onEdit}
                className="px-4 py-2 min-h-[2.75rem] rounded-field bg-navy text-ivory text-sm font-display font-medium hover:bg-navy-mid transition-colors"
              >
                {t('trips.preview.edit')}
              </button>
            )}
          </footer>
        )}
      </div>
    </div>
  )
}
