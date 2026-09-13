import { useTranslation } from 'react-i18next'
import { daysToDeparture, departureState, type Trip } from '../api/trips'

/**
 * T3.11.27 — «нужен указатель если рейс очень скоро и осталось мало времени.
 * Например трое суток светло зелёным и оранжевым за сутки» (owner, 2026-09-12).
 *
 * A date is not a deadline. «14 сентября, 21:40» tells somebody scanning a board
 * nothing about whether they still have time to pack and get across a city — it
 * asks them to do the arithmetic, once per card, against a clock they have to
 * remember. The colour answers it before the text is read.
 *
 * Two steps and no more: three days and one day. A gradient of urgency would be
 * a scale nobody has been taught, and amber on this palette already means «pay
 * attention» rather than «danger» (DESIGNGUIDELINES) — which is exactly the
 * weight «осталось меньше суток» deserves. Everything further out is silent:
 * a chip on every card is a chip that means nothing.
 *
 * Colour is never the only carrier of the message — the chip says how long in
 * words too (WCAG 2.2 AA, and a board read in sunlight on a phone). The text
 * itself stays navy for the same reason: amber on a pale amber ground is about
 * 2.9:1, which is a signal you can see and cannot read.
 *
 * Functions (PROJECT §6.2a):
 * - `DepartureChip({ trip })` — default export. Called by: `pages/TripsPage`,
 *   `pages/DashboardPage`, `components/TripPreview`.
 */
interface Props {
  trip: Pick<Trip, 'depart_at' | 'expires_at'>
  /** Fixed «now», for tests. */
  now?: number
}

export default function DepartureChip({ trip, now }: Props) {
  const { t } = useTranslation()
  const state = departureState(trip, now)

  if (state === 'later') return null

  if (state === 'flown') {
    return (
      <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-navy/5 text-navy/40">
        {t('trips.departure.flown')}
      </span>
    )
  }

  const imminent = state === 'imminent'
  return (
    <span
      className={`text-[11px] font-mono px-2 py-0.5 rounded-full ${
        imminent
          ? 'bg-amber/20 text-navy border border-amber/50'
          : 'bg-success/10 text-navy border border-success/40'
      }`}
    >
      {imminent
        ? t('trips.departure.imminent')
        : t('trips.departure.soon', { count: daysToDeparture(trip, now) })}
    </span>
  )
}
