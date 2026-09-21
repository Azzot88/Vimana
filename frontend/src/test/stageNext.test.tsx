import { describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import DealStages from '../components/DealStages'
import type { VaultMessage } from '../api/dealvault'
import type { DealDetail } from '../api/deals'
import { renderWithProviders } from './render'

/**
 * T_UX.28 пп. 6–7, 9 (owner, 2026-09-19).
 *
 * Three things the deal screen knew and did not say:
 *   «На странице статуса всегда должна быть информация о следующем
 *   запланированном статусе. Если вылетел, то надо писать когда прилёт и куда…
 *   Эти данные все есть, их надо показывать.»
 *   «Если статус вылетел нажат, то его нельзя нажать во второй раз.»
 *   And a meeting somebody has proposed used to be invisible until answered.
 */
vi.mock('../api/terms', async () => {
  const actual = await vi.importActual<typeof import('../api/terms')>('../api/terms')
  return { ...actual, raiseCard: vi.fn(), raiseCardWithFiles: vi.fn() }
})

const msg = (over: Partial<VaultMessage>): VaultMessage =>
  ({
    id: over.id ?? 'm1',
    deal_id: 'd1',
    sender_id: 'u1',
    text: null,
    created_at: '2026-09-20T10:00:00Z',
    attachments: [],
    card_kind: null,
    card_payload: null,
    card_state: null,
    requires_ack_by: null,
    ...over,
  }) as VaultMessage

const deal = (over: Partial<DealDetail> = {}): DealDetail =>
  ({
    id: 'd1',
    status: 'in_transit',
    sender_id: 's1',
    carrier_id: 'c1',
    recipient_id: null,
    trip_segments: [
      {
        order: 0,
        origin: 'DXB',
        destination: 'JFK',
        depart_at: '2026-09-21T08:00:00Z',
        arrive_at: '2026-09-21T18:30:00Z',
        origin_city: 'Dubai',
        destination_city: 'New York',
      },
    ],
    ...over,
  }) as DealDetail

const stages = (over: {
  messages?: VaultMessage[]
  deal?: DealDetail | null
  myRole?: 'sender' | 'carrier'
}) =>
  renderWithProviders(
    <DealStages
      dealId="d1"
      status="in_transit"
      myRole={over.myRole ?? 'carrier'}
      terms={null}
      deal={over.deal === undefined ? deal() : over.deal}
      messages={over.messages ?? []}
      onDone={() => {}}
    />,
  )

describe('the next planned step', () => {
  it('names where and when the flight lands while it is in the air', () => {
    stages({
      messages: [
        msg({
          card_kind: 'transit.update',
          card_state: 'accepted',
          card_payload: { stage: 'departed' },
        }),
      ],
    })
    expect(screen.getByText(/New York/)).toBeInTheDocument()
  })

  it('says nothing it does not know: a trip with no legs gets no line', () => {
    // An empty «Дальше:» is worse than silence — it reads as a step nobody
    // planned rather than as data we do not have.
    stages({ deal: deal({ trip_segments: [] }) })
    expect(screen.queryByText(/Next:|Дальше:/)).not.toBeInTheDocument()
  })
})

describe('the journey statuses', () => {
  it('stops offering a departure once it has been declared', () => {
    /* T_UX.29 п.2 — and it is still **shown**. Silently dropping it made the
       row shrink with no explanation; the owner asked for the opposite, that
       the journey so far read off the card. So it stays, as a record with a
       tick and nothing to press. */
    stages({
      messages: [
        msg({
          card_kind: 'transit.update',
          card_state: 'accepted',
          card_payload: { stage: 'departed' },
        }),
      ],
    })
    expect(
      screen.queryByRole('button', { name: /^Departed$|^Вылетел$/ }),
    ).not.toBeInTheDocument()
    expect(screen.getByText(/^Departed$|^Вылетел$/)).toBeInTheDocument()
    // The layover is still on, because the parcel has not landed.
    expect(screen.getByText(/^Layover$|^Пересадка$/)).toBeInTheDocument()
  })

  it('takes the layover away after the landing', () => {
    /* «Пересадка… строго до того как прилетел. После прилёта Пересадка
       невозможна» — so it is not offered, rather than offered and refused. */
    stages({
      messages: [
        msg({
          card_kind: 'transit.update',
          card_state: 'accepted',
          card_payload: { stage: 'arrived' },
        }),
      ],
    })
    expect(screen.queryByText(/^Layover$|^Пересадка$/)).not.toBeInTheDocument()
  })

  it('does not invent a stop the carrier never declared', () => {
    /* T_UX.29 п.2 — the record is what this deal said, not everything the
       order puts behind the furthest milestone. A landing announced without a
       layover has not had one, and «Пересадка ✓» over it would be the screen
       adding a stop to somebody's journey. */
    stages({
      messages: [
        msg({
          card_kind: 'transit.update',
          card_state: 'accepted',
          card_payload: { stage: 'arrived' },
        }),
      ],
    })
    expect(screen.queryByText(/^Departed$|^Вылетел$/)).not.toBeInTheDocument()
    expect(screen.queryByText(/^Layover$|^Пересадка$/)).not.toBeInTheDocument()
  })
})
