import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import DealAgreementCard from '../components/DealAgreementCard'
import DealStages from '../components/DealStages'
import type { DealDetail } from '../api/deals'
import { roleIn } from '../lib/dealRole'
import { renderWithProviders } from './render'
import i18n from '../i18n'

/**
 * T3.12.01 — the recipient is a role, not a guest in somebody else's chat.
 *
 * Разбор 2026-09-13: every screen worked out the reader's role as «carrier, or
 * else sender», so the recipient came out as the sender in lists and as nobody
 * on the deal screen — and the delivery the server addressed to them had no
 * button anywhere. These pin the three places that answer drifted.
 */
const en = i18n.getFixedT('en')

const detail = (over: Partial<DealDetail> = {}): DealDetail =>
  ({
    id: 'd1',
    order_id: 'o1',
    trip_id: 't1',
    sender_id: 'u-sender',
    carrier_id: 'u-carrier',
    recipient_id: null,
    recipient_name: null,
    status: 'accepted',
    created_at: '2026-09-13T10:00:00Z',
    origin: 'DXB',
    destination: 'JFK',
    depart_at: '2026-09-20T10:00:00Z',
    sender_name: 'Anna',
    carrier_name: 'Boris',
    cargo_description: '',
    cargo_category: 'document',
    declared_value: 0,
    currency: 'USD',
    ...over,
  }) as DealDetail

describe('roleIn', () => {
  const deal = { sender_id: 's', carrier_id: 'c', recipient_id: 'r' }

  it('names each side of the deal', () => {
    expect(roleIn(deal, 's')).toBe('sender')
    expect(roleIn(deal, 'c')).toBe('carrier')
    expect(roleIn(deal, 'r')).toBe('recipient')
  })

  it('reads a sender who named themselves the recipient as the sender', () => {
    expect(roleIn({ ...deal, recipient_id: 's' }, 's')).toBe('sender')
  })

  it('gives nobody a role in a deal without a recipient', () => {
    expect(roleIn({ ...deal, recipient_id: null }, 'r')).toBeNull()
  })

  it('has no answer for an outsider or a signed-out reader', () => {
    expect(roleIn(deal, 'x')).toBeNull()
    expect(roleIn(deal, undefined)).toBeNull()
    expect(roleIn(null, 's')).toBeNull()
  })
})

describe('deal header', () => {
  const noop = () => {}

  it('names the recipient', () => {
    renderWithProviders(
      <DealAgreementCard
        deal={detail({ recipient_id: 'u-r', recipient_name: 'Vera' })}
        terms={null}
        open={false}
        onToggle={noop}
      />,
    )
    expect(screen.getByText(/Anna → Boris → Vera/)).toBeInTheDocument()
  })

  it('names the recipient even when it is the sender', () => {
    renderWithProviders(
      <DealAgreementCard
        deal={detail({ recipient_id: 'u-sender', recipient_name: 'Anna' })}
        terms={null}
        open={false}
        onToggle={noop}
      />,
    )
    expect(screen.getByText(/Anna → Boris → Anna/)).toBeInTheDocument()
  })

  it('says in words that nobody is named yet', () => {
    renderWithProviders(
      <DealAgreementCard deal={detail()} terms={null} open={false} onToggle={noop} />,
    )
    expect(
      screen.getByText(new RegExp(en('agreement.noRecipient') as string)),
    ).toBeInTheDocument()
  })
})

describe('dispute on a delivered deal', () => {
  const stages = (myRole: 'sender' | 'recipient') => (
    <DealStages
      dealId="d1"
      status="delivered"
      myRole={myRole}
      terms={null}
      deal={null}
      messages={[]}
      onDone={() => {}}
    />
  )

  it('is offered to the sender', () => {
    renderWithProviders(stages('sender'))
    expect(
      screen.queryAllByText(en('dispute.openButton') as string).length,
    ).toBeGreaterThan(0)
  })

  it('is not offered to the recipient, whom the server would refuse', () => {
    renderWithProviders(stages('recipient'))
    expect(screen.queryByText(en('dispute.openButton') as string)).toBeNull()
  })
})
