import { describe, expect, it } from 'vitest'
import ArchiveRecordCard from '../components/ArchiveRecordCard'
import type { ArchiveRecord } from '../api/trust'
import { renderWithProviders } from './render'

/**
 * T3.19 — the placard under a retired identity.
 *
 * These tests guard the claims, not the layout. A card that renders beautifully
 * while promising a measurement nobody made is the failure mode this task was
 * written against, and it is invisible to a snapshot.
 */
const record = (over: Partial<ArchiveRecord> = {}): ArchiveRecord => ({
  retired_at: '2026-07-01T00:00:00Z',
  chain_entries: 40,
  signatures: 31,
  first_signature_at: '2025-02-03T00:00:00Z',
  last_signature_at: '2026-06-28T00:00:00Z',
  deals_total: 15,
  deals_closed: 12,
  routes_measured: 9,
  routes_closed: 12,
  straight_line_km: 41230,
  longest_hop_km: 7180,
  longest_hop_route: 'TBS→ULN',
  trips_completed: 7,
  capacity_kg: 48.5,
  last_anchor_at: null,
  anchored_deals: 0,
  ...over,
})

describe('ArchiveRecordCard', () => {
  it('shows every total next to the set it was counted from', () => {
    const { container } = renderWithProviders(<ArchiveRecordCard record={record()} />)
    const text = container.textContent ?? ''
    // "12 of 15", not a bare 12 that invites the reader to supply a denominator.
    expect(text).toContain('12 closed of 15')
    expect(text).toContain('31 of 40 chain entries')
    expect(text).toContain('measured on 9 routes of 12')
  })

  it('says "straight line" on every distance label', () => {
    const { container } = renderWithProviders(<ArchiveRecordCard record={record()} />)
    const text = container.textContent ?? ''
    // Both the routes total and the longest hop. The arc is not the track, and
    // a label that dropped this would be naming a different measurement.
    expect(text).toContain('Routes, km straight line')
    expect(text).toContain('Longest hop, km straight line')
  })

  it('omits a distance it could not measure instead of printing zero', () => {
    const { container } = renderWithProviders(
      <ArchiveRecordCard
        record={record({
          routes_measured: 0,
          straight_line_km: null,
          longest_hop_km: null,
          longest_hop_route: null,
        })}
      />,
    )
    const text = container.textContent ?? ''
    // A confident "0 km" would assert a measurement that never happened.
    expect(text).not.toContain('Routes, km straight line')
    expect(text).not.toContain('Longest hop, km straight line')
    // Deals and signatures are still counted, so the card is not empty.
    expect(text).toContain('12 closed of 15')
  })

  it('claims nothing about independent checking until an anchor exists', () => {
    const { queryByTestId } = renderWithProviders(<ArchiveRecordCard record={record()} />)
    // T3.20 — with no anchor there is no third party holding anything, and
    // "independently checkable" with no date behind it is the exact claim this
    // project refuses to make.
    expect(queryByTestId('archive-anchor')).toBeNull()
  })

  it('dates the claim and stops it at the anchor', () => {
    const { getByTestId } = renderWithProviders(
      <ArchiveRecordCard
        record={record({ last_anchor_at: '2026-06-30T00:00:00Z', anchored_deals: 11 })}
      />,
    )
    const text = getByTestId('archive-anchor').textContent ?? ''
    expect(text).toContain('11 of 15')
    // The boundary is stated, not implied: what came after the anchor rests on
    // our own integrity check alone.
    expect(text).toContain('after that date')
    expect(text).not.toContain('forever')
  })

  it('never promises that anything is verified forever', () => {
    const { container } = renderWithProviders(<ArchiveRecordCard record={record()} />)
    const text = (container.textContent ?? '').toLowerCase()
    // The chain is tamper-evident, not tamper-proof. The wording that would be
    // true — independently checkable as of the last anchor — needs anchors
    // switched on (T3.20) and their date.
    expect(text).not.toContain('forever')
    expect(text).not.toContain('tamper-proof')
    expect(text).not.toContain('guaranteed')
  })
})
