import { describe, expect, it } from 'vitest'

import { routeChain } from '../lib/format'

/** T3.11.07 — the trip card's route line.
 *
 *  The case worth pinning is the multi-leg one: `Trip.origin` / `destination`
 *  are the head and tail of the chain, so a card built from them alone reads
 *  correctly and silently drops every city in between — and 15 % of real
 *  listings on this market have cities in between.
 */
describe('routeChain', () => {
  it('prints a single flight as origin → destination', () => {
    expect(
      routeChain({
        origin: 'DXB',
        destination: 'JFK',
        legs: [{ origin: 'DXB', destination: 'JFK' }],
      }),
    ).toBe('DXB → JFK')
  })

  it('prints every node of a chain', () => {
    expect(
      routeChain({
        origin: 'SVO',
        destination: 'PDX',
        legs: [
          { origin: 'SVO', destination: 'MIA' },
          { origin: 'MIA', destination: 'LAX' },
          { origin: 'LAX', destination: 'PDX' },
        ],
      }),
    ).toBe('SVO → MIA → LAX → PDX')
  })

  it('falls back to the denormalised pair when legs are absent', () => {
    // A trip fetched by an older cached response, or any caller that has the
    // headline and not the chain. The line still has to render.
    expect(routeChain({ origin: 'IST', destination: 'LED' })).toBe('IST → LED')
  })

  it('shows a there-and-back chain as three nodes, not two', () => {
    // 36.6 % of real posts carry the return flight in the same listing, and
    // collapsing it to `SVO → SVO` would be the one summary that says nothing.
    expect(
      routeChain({
        origin: 'SVO',
        destination: 'SVO',
        legs: [
          { origin: 'SVO', destination: 'DXB' },
          { origin: 'DXB', destination: 'SVO' },
        ],
      }),
    ).toBe('SVO → DXB → SVO')
  })
})

/** T3.11.07 — the city in front of the code (owner's decision 2026-09-06). */
describe('routeChain with cities', () => {
  it('prints «city, code» when the API resolved one', () => {
    expect(
      routeChain({
        origin: 'JFK',
        destination: 'DME',
        legs: [
          {
            origin: 'JFK',
            destination: 'DXB',
            origin_city: 'New York',
            destination_city: 'Dubai',
          },
          {
            origin: 'DXB',
            destination: 'DME',
            origin_city: 'Dubai',
            destination_city: 'Moscow',
          },
        ],
      }),
    ).toBe('New York, JFK → Dubai, DXB → Moscow, DME')
  })

  it('keeps the city on a single flight', () => {
    // The old guard fell back to the denormalised pair for anything under two
    // legs, which threw the city away on every direct flight — the commonest
    // shape on this market.
    expect(
      routeChain({
        origin: 'DXB',
        destination: 'JFK',
        legs: [
          {
            origin: 'DXB',
            destination: 'JFK',
            origin_city: 'Dubai',
            destination_city: 'New York',
          },
        ],
      }),
    ).toBe('Dubai, DXB → New York, JFK')
  })

  it('prints the code alone for a city we do not know', () => {
    // A code typed by hand rather than picked, or one the airport table has no
    // row for. The line still has to render, and a code alone is never wrong.
    expect(
      routeChain({
        origin: 'DXB',
        destination: 'ZZZ',
        legs: [
          { origin: 'DXB', destination: 'ZZZ', origin_city: 'Dubai', destination_city: null },
        ],
      }),
    ).toBe('Dubai, DXB → ZZZ')
  })
})
