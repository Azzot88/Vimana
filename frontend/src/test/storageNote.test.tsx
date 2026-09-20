import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import StorageNote from '../components/StorageNote'
import { renderWithProviders } from './render'

/**
 * T_DEAL.1 — «ожидание, иногда платное» (owner, 2026-09-20).
 *
 * What is pinned here is what the owner asked the status to say: до когда
 * бесплатно, сколько набежало, и — отдельно — сколько назвал перевозчик. The
 * last one is a different number by design: «счётчик уведомительный, и сумма за
 * хранение может быть изменена», so a screen that merged them would be telling
 * the sender the carrier had charged something they had not.
 */
const base = {
  started_at: '2026-09-18T12:00:00Z',
  free_days: 2,
  free_until: '2026-09-21T06:00:00Z',
  nights: 1,
  paid_days: 0,
  price: 1,
  unit: 'kg' as const,
  units: 3,
  currency: 'USD',
  amount: 0,
  max_paid_days: 14,
  capped: false,
  charged: null,
}

describe('the storage note', () => {
  it('while it is free, says until when', () => {
    renderWithProviders(<StorageNote storage={base} />)
    expect(screen.getByText(/Free until|Бесплатно до/i)).toBeInTheDocument()
    // Nothing is owed yet, so no accrual line pretends otherwise.
    expect(screen.queryByText(/Accrued|Начислено/i)).not.toBeInTheDocument()
  })

  it('once it is paid, shows the days and the sum', () => {
    renderWithProviders(
      <StorageNote storage={{ ...base, paid_days: 3, amount: 9, nights: 5 }} />,
    )
    expect(screen.getByText(/Accrued|Начислено/i)).toBeInTheDocument()
    expect(screen.getByText('9 USD')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
  })

  it('says the weight is missing rather than showing a nought', () => {
    /* A nought here is a free storage nobody agreed to: the tariff is per
       kilogram and the cargo was never weighed. */
    renderWithProviders(
      <StorageNote storage={{ ...base, paid_days: 2, amount: null, units: null }} />,
    )
    expect(
      screen.getByText(/weight not stated|вес не указан/i),
    ).toBeInTheDocument()
  })

  it('announces the ceiling instead of letting the sum run on', () => {
    renderWithProviders(
      <StorageNote
        storage={{ ...base, paid_days: 14, amount: 42, capped: true }}
      />,
    )
    expect(
      screen.getByText(/ceiling is reached|Достигнут предел/i),
    ).toBeInTheDocument()
  })

  it('keeps the carrier’s own charge apart from the counter', () => {
    renderWithProviders(
      <StorageNote
        storage={{
          ...base,
          paid_days: 5,
          amount: 15,
          charged: { days: 3, amount: 9, currency: 'USD', state: 'pending' },
        }}
      />,
    )
    // The counter says fifteen, the carrier charged nine, and both are on the
    // card: that gap is the owner's rule, not a bug to reconcile.
    expect(screen.getByText('15 USD')).toBeInTheDocument()
    expect(screen.getByText('9 USD')).toBeInTheDocument()
    expect(
      screen.getByText(/awaiting your answer|ждёт подтверждения/i),
    ).toBeInTheDocument()
  })

  it('says the counter is only a notice while nothing is charged', () => {
    renderWithProviders(<StorageNote storage={{ ...base, paid_days: 2, amount: 6 }} />)
    expect(
      screen.getByText(/counter is a notice|Счётчик уведомительный/i),
    ).toBeInTheDocument()
  })
})
