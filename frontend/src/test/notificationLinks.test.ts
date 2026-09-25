import { describe, expect, it } from 'vitest'
import type { AppNotification } from '../api/notifications'
import {
  corridorFromQuery,
  hrefFor,
  newTripFor,
  routeOf,
} from '../lib/notificationLinks'
import en from '../i18n/locales/en.json'
import ru from '../i18n/locales/ru.json'
import ua from '../i18n/locales/ua.json'
import pl from '../i18n/locales/pl.json'
import fr from '../i18n/locales/fr.json'
import es from '../i18n/locales/es.json'

/**
 * T_UX.31 — a bell row leads to where something can be done about it.
 *
 * Ревизия путей R6: «somebody is asking for your corridor» opened
 * `/notifications`, which the app does not route, and no row ever led to one
 * trip. These pin every kind the server writes to an address the app has.
 */
const row = (over: Partial<AppNotification>): AppNotification => ({
  id: 'n1',
  kind: 'deal.status',
  deal_id: null,
  trip_id: null,
  payload: null,
  created_at: '2026-09-24T10:00:00Z',
  read_at: null,
  ...over,
})

/** Every kind `models/notification.NotificationKind` declares. */
const KINDS = [
  'chat.message',
  'trip.response',
  'request.new',
  'deal.status',
  'trip.corridor',
  'recipient.offer',
  'dispute.offer',
] as const

describe('hrefFor', () => {
  it('takes deal rows into the deal', () => {
    for (const kind of ['chat.message', 'trip.response', 'deal.status']) {
      expect(hrefFor(row({ kind, deal_id: 'd1' }))).toBe('/deals/d1/vault')
    }
  })

  it('takes a trip on your corridor to the page where you answer it', () => {
    expect(hrefFor(row({ kind: 'trip.corridor', trip_id: 't1' }))).toBe('/trips/t1/respond')
  })

  it('takes a carrier from a corridor request to the wizard with the corridor filled in', () => {
    expect(
      hrefFor(row({ kind: 'request.new', payload: { origin: 'LAX', destination: 'SVO' } })),
    ).toBe('/trips/new?from=LAX&to=SVO')
  })

  it('takes a recipient offer to the account and a dispute offer to the queue', () => {
    expect(hrefFor(row({ kind: 'recipient.offer' }))).toBe('/profile')
    expect(hrefFor(row({ kind: 'dispute.offer' }))).toBe('/disputes')
  })

  it('never leads to an address the app does not route', () => {
    for (const kind of KINDS) {
      for (const shape of [
        row({ kind }),
        row({ kind, deal_id: 'd1' }),
        row({ kind, trip_id: 't1' }),
      ]) {
        const href = hrefFor(shape)
        expect(href.startsWith('/notifications')).toBe(false)
        expect(href.startsWith('/admin')).toBe(false)
      }
    }
  })
})

describe('routeOf', () => {
  it('reads a route or an origin–destination pair, and nothing else', () => {
    expect(routeOf(row({ payload: { route: 'DXB → JFK' } }))).toBe('DXB → JFK')
    expect(routeOf(row({ payload: { origin: 'LAX', destination: 'SVO' } }))).toBe('LAX → SVO')
    expect(routeOf(row({ payload: { deal_no: 'PF-1' } }))).toBeNull()
    expect(routeOf(row({}))).toBeNull()
  })
})

describe('corridorFromQuery', () => {
  it('reads back what the bell wrote', () => {
    const query = new URLSearchParams(newTripFor('LAX', 'SVO').split('?')[1])
    expect(corridorFromQuery(query.get('from'), query.get('to'))).toEqual({
      origin: 'LAX',
      destination: 'SVO',
    })
  })

  it('accepts lower case and ignores what is not an airport pair', () => {
    expect(corridorFromQuery('lax', 'svo')).toEqual({ origin: 'LAX', destination: 'SVO' })
    expect(corridorFromQuery(null, 'SVO')).toBeNull()
    expect(corridorFromQuery('LAX', 'LAX')).toBeNull()
    expect(corridorFromQuery('LA', 'SVO')).toBeNull()
    expect(corridorFromQuery('<script>', 'SVO')).toBeNull()
  })
})

describe('bell labels', () => {
  it('names every kind in all six languages', () => {
    for (const [name, locale] of Object.entries({ en, ru, ua, pl, fr, es })) {
      const labels = (locale as { notifications: { kind: Record<string, string> } })
        .notifications.kind
      for (const kind of KINDS) {
        expect(labels[kind.replace('.', '_')], `${name}: ${kind}`).toBeTruthy()
      }
    }
  })
})
