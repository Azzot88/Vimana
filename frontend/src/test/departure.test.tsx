import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import DepartureChip from '../components/DepartureChip'
import { daysToDeparture, departureState, type Trip } from '../api/trips'
import { renderWithProviders } from './render'

/**
 * T3.11.27 — «Рейсы должны уходить в архив, если прошла дата вылета. Также нужен
 * указатель если рейс очень скоро и осталось мало времени. Например трое суток
 * светло зелёным и оранжевым за сутки» (owner, 2026-09-12).
 *
 * Both halves are one function, and its edges are where the damage is: a trip
 * archived an hour early disappears from under the carrier who is about to fly
 * it, and one archived late keeps offering a sender a flight that has left.
 */
const NOW = Date.parse('2026-09-12T12:00:00Z')
const hours = (n: number) => new Date(NOW + n * 3600_000).toISOString()

const trip = (over: Partial<Trip>): Pick<Trip, 'depart_at' | 'expires_at'> => ({
  depart_at: hours(100),
  expires_at: null,
  ...over,
})

describe('departureState', () => {
  it('calls a trip flown once its last departure is behind us', () => {
    expect(departureState(trip({ depart_at: hours(-1) }), NOW)).toBe('flown')
  })

  it('keeps a chain alive while its second flight is still ahead', () => {
    /* The first leg left this morning; the connection is tomorrow. Judging this
       by `depart_at` would archive a trip the carrier is in the middle of — so
       `expires_at`, the last leg, decides, exactly as the board does
       server-side. */
    expect(
      departureState(
        trip({ depart_at: hours(-3), expires_at: hours(20) }),
        NOW,
      ),
    ).toBe('imminent')
  })

  it('is orange inside a day and green inside three', () => {
    expect(departureState(trip({ depart_at: hours(23) }), NOW)).toBe('imminent')
    expect(departureState(trip({ depart_at: hours(25) }), NOW)).toBe('soon')
    expect(departureState(trip({ depart_at: hours(71) }), NOW)).toBe('soon')
  })

  it('says nothing about a flight that is a week out', () => {
    // A chip on every card is a chip that means nothing.
    expect(departureState(trip({ depart_at: hours(24 * 7) }), NOW)).toBe('later')
  })

  it('never archives a trip it cannot date', () => {
    // Same choice the server made: hiding rows we cannot date would be guessing.
    expect(
      departureState({ depart_at: '', expires_at: null } as never, NOW),
    ).toBe('later')
  })

  it('rounds the days to the nearest, never generously', () => {
    // 25 hours is a day, not two: on this chip an overstatement is the one
    // error that costs somebody the flight.
    expect(daysToDeparture(trip({ depart_at: hours(25) }), NOW)).toBe(1)
    expect(daysToDeparture(trip({ depart_at: hours(50) }), NOW)).toBe(2)
    expect(daysToDeparture(trip({ depart_at: hours(71) }), NOW)).toBe(3)
  })
})

describe('DepartureChip', () => {
  it('draws nothing for a distant flight', () => {
    const { container } = renderWithProviders(
      <DepartureChip trip={trip({ depart_at: hours(24 * 9) })} now={NOW} />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('says how little time is left, and not only in colour', () => {
    renderWithProviders(
      <DepartureChip trip={trip({ depart_at: hours(5) })} now={NOW} />,
    )
    expect(
      screen.getByText(/less than a day|Меньше суток/i),
    ).toBeInTheDocument()
  })

  it('counts the remaining days when there are a few', () => {
    renderWithProviders(
      <DepartureChip trip={trip({ depart_at: hours(50) })} now={NOW} />,
    )
    expect(screen.getByText(/2/)).toBeInTheDocument()
  })

  it('marks a flight that has already gone', () => {
    renderWithProviders(
      <DepartureChip trip={trip({ depart_at: hours(-48) })} now={NOW} />,
    )
    expect(screen.getByText(/departed|Вылетел/i)).toBeInTheDocument()
  })
})
