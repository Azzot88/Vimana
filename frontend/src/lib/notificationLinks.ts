import type { AppNotification } from '../api/notifications'

/**
 * T_UX.31 — where a notification takes the person, decided by what it is about.
 *
 * The bell used to answer by the shape of the row: a deal id → the deal, a trip
 * id → the whole board, anything else → `/notifications`, which is not an
 * address the app has. So a carrier told «somebody is asking for your corridor»
 * pressed it and got the 404 page, and nothing ever pointed at a single trip.
 * Ревизия путей R6, S13.
 *
 * The wizard's corridor address is built and read here too: the bell writes
 * it and `NewTripPage` reads it, and two spellings of one address are how the
 * recipient link lost its way (`T_UX.30`).
 *
 * Functions (PROJECT §6.2a):
 * - `hrefFor(n)` — the address a bell row opens. Called by: `NotificationBell`.
 * - `routeOf(n)` — «LAX → SVO» from the row's payload, or null. Called by:
 *   `NotificationBell`.
 * - `newTripFor(origin, destination)` — the wizard with a corridor filled in.
 *   Called by: `hrefFor`.
 * - `corridorFromQuery(from, to)` — the corridor the wizard was asked to start
 *   with, or null when the address does not carry a usable one. Called by:
 *   `NewTripPage`.
 */

const IATA = /^[A-Z]{3}$/

function text(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

export function newTripFor(origin: string, destination: string): string {
  const query = new URLSearchParams({ from: origin, to: destination })
  return `/trips/new?${query.toString()}`
}

export function corridorFromQuery(
  from: string | null,
  to: string | null,
): { origin: string; destination: string } | null {
  const origin = (from ?? '').trim().toUpperCase()
  const destination = (to ?? '').trim().toUpperCase()
  if (!IATA.test(origin) || !IATA.test(destination) || origin === destination) return null
  return { origin, destination }
}

export function hrefFor(n: AppNotification): string {
  switch (n.kind) {
    case 'trip.corridor':
      // A trip exists and the person asked for it: the page where they answer
      // it, which shows the trip above the form.
      return n.trip_id ? `/trips/${n.trip_id}/respond` : '/trips'
    case 'request.new': {
      // A sender is waiting on a corridor: what a carrier can do about it is
      // publish a trip there.
      const origin = text(n.payload?.origin)
      const destination = text(n.payload?.destination)
      return origin && destination ? newTripFor(origin, destination) : '/trips/new'
    }
    case 'recipient.offer':
      // The offer is answered in the account, not in a deal that is not yet
      // theirs to open.
      return '/profile'
    case 'dispute.offer':
      return '/disputes'
    default:
      // Chat messages, card moves and responses all belong to a deal. A row
      // without one has nowhere better than the panel — never an address the
      // app does not route.
      return n.deal_id ? `/deals/${n.deal_id}/vault` : '/dashboard'
  }
}

export function routeOf(n: AppNotification): string | null {
  const route = text(n.payload?.route)
  if (route) return route
  const origin = text(n.payload?.origin)
  const destination = text(n.payload?.destination)
  return origin && destination ? `${origin} → ${destination}` : null
}
