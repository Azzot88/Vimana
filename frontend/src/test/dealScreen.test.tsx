import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import CargoRouteCard from '../components/CargoRouteCard'
import DealAgreementCard from '../components/DealAgreementCard'
import { stageOf } from '../lib/dealStages'
import type { DealDetail } from '../api/deals'
import type { Terms } from '../api/terms'
import { renderWithProviders } from './render'
import i18n from '../i18n'

/**
 * T3.12.10 — the deal screen: the cargo's route above it, and whose move the
 * agreement is on.
 *
 * Owner, 2026-09-15: a route card with the shipment number and this deal named
 * on the line; every terms field is open to both sides, so the card marks the
 * answer rather than the ownership of a field.
 */
const t = i18n.t.bind(i18n)

const deal = (over: Partial<DealDetail> = {}): DealDetail =>
  ({
    id: 'd1',
    cargo_id: 'c1',
    trip_id: 't1',
    sender_id: 's1',
    carrier_id: 'c2',
    recipient_id: null,
    status: 'in_transit',
    created_at: '2026-09-15T00:00:00Z',
    origin: 'DXB',
    destination: 'JFK',
    depart_at: '2026-09-20T10:00:00Z',
    sender_name: 'Sam',
    carrier_name: 'Cara',
    recipient_name: null,
    cargo_description: 'papers',
    cargo_category: 'document',
    declared_value: 100,
    currency: 'USD',
    deal_no: 'PF-482-19375-1',
    ...over,
  }) as DealDetail

const terms = (over: Partial<Terms> = {}): Terms =>
  ({
    id: 'm1',
    deal_id: 'd1',
    card_kind: 'terms.proposed',
    card_state: 'pending',
    requires_ack_by: 'carrier',
    supersedes_id: null,
    payload: { price_total: 120, currency: 'USD' },
    description: null,
    created_at: '2026-09-15T00:00:00Z',
    ...over,
  }) as Terms

describe('CargoRouteCard', () => {
  it('names the number, both ends and this deal', () => {
    renderWithProviders(<CargoRouteCard deal={deal()} />)
    expect(screen.getByText('№ PF-482-19375-1')).toBeInTheDocument()
    expect(screen.getByText('DXB')).toBeInTheDocument()
    expect(screen.getByText('JFK')).toBeInTheDocument()
    expect(screen.getByText(t('cargoRoute.thisDeal'))).toBeInTheDocument()
  })

  it('says where the cargo is when the server says so', () => {
    renderWithProviders(
      <CargoRouteCard deal={deal({ cargo_location: 'with_postal_service' })} />,
    )
    expect(
      screen.getByText(t('cargoRoute.where.with_postal_service')),
    ).toBeInTheDocument()
  })
})

describe('DealAgreementCard · whose move', () => {
  const card = (over: Partial<Terms> | null, myRole: 'sender' | 'carrier') =>
    renderWithProviders(
      <DealAgreementCard
        deal={deal()}
        terms={over === null ? null : terms(over)}
        myRole={myRole}
        open={false}
        onToggle={() => {}}
      />,
    )

  it('tells the addressee it is their answer', () => {
    card({ requires_ack_by: 'carrier' }, 'carrier')
    expect(screen.getByText(t('agreement.answer.yourTurn'))).toBeInTheDocument()
  })

  it('names the other side when it is not', () => {
    card({ requires_ack_by: 'carrier' }, 'sender')
    expect(
      screen.getByText(
        t('agreement.answer.waiting', { who: t('agreement.role.carrier') }),
      ),
    ).toBeInTheDocument()
  })

  it('says nothing is pending once the terms are agreed', () => {
    card({ card_kind: 'terms.agreed', card_state: 'accepted', requires_ack_by: null }, 'sender')
    expect(screen.getByText(t('agreement.answer.agreed'))).toBeInTheDocument()
  })

  it('stays quiet before anything is proposed', () => {
    card(null, 'sender')
    expect(screen.queryByText(t('agreement.answer.agreed'))).not.toBeInTheDocument()
  })
})

describe('stageOf · a posted deal paid before it arrived', () => {
  it('stands on delivery, not closed', () => {
    expect(stageOf('confirmed', { posted: true })).toBe('delivery')
    expect(stageOf('confirmed')).toBe('closed')
  })
})
