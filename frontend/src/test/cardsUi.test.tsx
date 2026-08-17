import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import TermsCard from '../components/TermsCard'
import DealCard from '../components/DealCard'
import CardActions from '../components/CardActions'
import type { VaultMessage } from '../api/dealvault'
import { buildPayload, formsForRole, specForKind } from '../lib/cardForms'
import { renderWithProviders } from './render'

/**
 * T3.34–T3.39 — the rules the UI is only allowed to *reflect*.
 *
 * One property runs through all of these and is the reason the file exists:
 * **a card that awaits the other side must not offer this user a button.** The
 * server refuses such an answer anyway (403), so a button here is not a
 * security hole — it is worse in a quieter way. It teaches people that half the
 * controls in a deal do nothing, and a control surface that lies is one nobody
 * reads when it finally matters.
 *
 * It also breaks silently: nothing fails when the condition drifts, the button
 * simply starts appearing. That is exactly the kind of regression a test has to
 * hold in place.
 */
vi.mock('../api/dealvault', async () => {
  const actual =
    await vi.importActual<typeof import('../api/dealvault')>('../api/dealvault')
  return { ...actual, ackCard: vi.fn(), uploadAttachment: vi.fn() }
})
vi.mock('../api/terms', async () => {
  const actual = await vi.importActual<typeof import('../api/terms')>('../api/terms')
  return { ...actual, raiseCard: vi.fn() }
})

import { ackCard, uploadAttachment } from '../api/dealvault'
import { raiseCard } from '../api/terms'

const msg = (over: Partial<VaultMessage> = {}): VaultMessage => ({
  id: 'm1',
  deal_id: 'd1',
  sender_id: 'u-sender',
  text: null,
  is_system: true,
  attachments: [],
  created_at: '2026-08-16T10:00:00Z',
  ...over,
})

beforeEach(() => {
  vi.mocked(ackCard).mockReset().mockResolvedValue(msg())
  vi.mocked(uploadAttachment).mockReset().mockResolvedValue({ data: {} } as never)
  vi.mocked(raiseCard).mockReset().mockResolvedValue({} as never)
})

// ── the contract ──────────────────────────────────────────────────────────

describe('TermsCard', () => {
  const proposal = (over: Partial<VaultMessage> = {}) =>
    msg({
      card_kind: 'terms.proposed',
      card_state: 'pending',
      requires_ack_by: 'carrier',
      card_payload: {
        price_total: 140,
        currency: 'USD',
        weight_kg: 4,
        declared_value: 1200,
        normalized: {
          direction: 'AE->US',
          route: 'DXB->JFK',
          distance_km: 11000,
          weight_kg: 4,
          chargeable_weight_kg: 4,
          price_total: 140,
          currency: 'USD',
          price_per_kg: 35,
          price_per_km: 0.0127,
        },
      },
      ...over,
    })

  it('offers the answer to the side that owes it', () => {
    renderWithProviders(
      <TermsCard msg={proposal()} dealId="d1" myRole="carrier" onChanged={() => {}} />,
    )
    expect(screen.getByText(/accept|Принять/i)).toBeInTheDocument()
  })

  it('offers no answer to the side that does not', () => {
    renderWithProviders(
      <TermsCard msg={proposal()} dealId="d1" myRole="sender" onChanged={() => {}} />,
    )
    expect(screen.queryByText(/^accept$|^Принять$/i)).not.toBeInTheDocument()
  })

  it('shows the comparable figures, not just the total', () => {
    // A total alone cannot be compared between two trips — per-kg and per-km
    // are the reason the server normalises at all.
    renderWithProviders(
      <TermsCard msg={proposal()} dealId="d1" myRole="carrier" onChanged={() => {}} />,
    )
    expect(screen.getByText('35')).toBeInTheDocument()
    expect(screen.getByText('AE->US')).toBeInTheDocument()
  })

  it('an agreed contract asks nobody for anything', () => {
    renderWithProviders(
      <TermsCard
        msg={proposal({ card_kind: 'terms.agreed', card_state: 'accepted', requires_ack_by: null })}
        dealId="d1"
        myRole="carrier"
        onChanged={() => {}}
      />,
    )
    expect(screen.queryByText(/^accept$|^Принять$/i)).not.toBeInTheDocument()
  })

  it('sends the decision and reports back', async () => {
    const onChanged = vi.fn()
    renderWithProviders(
      <TermsCard msg={proposal()} dealId="d1" myRole="carrier" onChanged={onChanged} />,
    )
    fireEvent.click(screen.getByText(/accept|Принять/i))
    await waitFor(() => expect(ackCard).toHaveBeenCalledWith('d1', 'm1', 'accepted'))
    await waitFor(() => expect(onChanged).toHaveBeenCalled())
  })

  it('flags a price the carrier had already ruled out', () => {
    const low = proposal()
    low.card_payload = { ...low.card_payload, below_carrier_minimum: true }
    renderWithProviders(
      <TermsCard msg={low} dealId="d1" myRole="carrier" onChanged={() => {}} />,
    )
    expect(screen.getByText(/minimum|минимума/i)).toBeInTheDocument()
  })
})

// ── every other card ──────────────────────────────────────────────────────

describe('DealCard', () => {
  const pickup = (over: Partial<VaultMessage> = {}) =>
    msg({
      card_kind: 'pickup.proposed',
      card_state: 'pending',
      requires_ack_by: 'carrier',
      card_payload: { method: 'in_person', city: 'Dubai' },
      ...over,
    })

  it('offers the answer only to the awaited side', () => {
    const { unmount } = renderWithProviders(
      <DealCard msg={pickup()} dealId="d1" myRole="carrier" mine={false} onChanged={() => {}} />,
    )
    expect(screen.getByText(/accept|Принять/i)).toBeInTheDocument()
    unmount()

    renderWithProviders(
      <DealCard msg={pickup()} dealId="d1" myRole="sender" mine onChanged={() => {}} />,
    )
    expect(screen.queryByText(/^accept$|^Принять$/i)).not.toBeInTheDocument()
  })

  it('translates enum values instead of printing raw keys', () => {
    renderWithProviders(
      <DealCard msg={pickup()} dealId="d1" myRole="carrier" mine={false} onChanged={() => {}} />,
    )
    expect(screen.queryByText('in_person')).not.toBeInTheDocument()
  })

  it('asks its author for the missing photo', () => {
    // A declaration without evidence looks finished to whoever wrote it and
    // cannot be confirmed by anyone — so it needs its own visible state.
    renderWithProviders(
      <DealCard
        msg={msg({
          card_kind: 'handoff.declared',
          card_state: 'pending',
          requires_ack_by: 'carrier',
          card_payload: { parcel_count: 1 },
        })}
        dealId="d1"
        myRole="sender"
        mine
        onChanged={() => {}}
      />,
    )
    expect(screen.getByText(/attach the photo|Приложите фото/i)).toBeInTheDocument()
  })

  it('tells the other side it is waiting on that photo', () => {
    renderWithProviders(
      <DealCard
        msg={msg({
          card_kind: 'handoff.declared',
          card_state: 'pending',
          requires_ack_by: 'carrier',
          card_payload: {},
        })}
        dealId="d1"
        myRole="carrier"
        mine={false}
        onChanged={() => {}}
      />,
    )
    expect(screen.getByText(/waiting for the photo|Ждём фото/i)).toBeInTheDocument()
    expect(screen.queryByText(/^accept$|^Принять$/i)).not.toBeInTheDocument()
  })

  it('surfaces the server refusal rather than a generic failure', async () => {
    vi.mocked(ackCard).mockRejectedValue({
      response: { data: { detail: 'This declaration has no photo attached yet' } },
    })
    renderWithProviders(
      <DealCard msg={pickup()} dealId="d1" myRole="carrier" mine={false} onChanged={() => {}} />,
    )
    fireEvent.click(screen.getByText(/accept|Принять/i))
    await waitFor(() =>
      expect(screen.getByText(/no photo attached/i)).toBeInTheDocument(),
    )
  })
})

// ── raising a card ────────────────────────────────────────────────────────

describe('CardActions', () => {
  it('offers only what this role may actually raise', () => {
    renderWithProviders(<CardActions dealId="d1" myRole="carrier" onDone={() => {}} />)
    // The carrier moves the cargo, so transit updates are theirs…
    expect(screen.getByText(/transit update|Статус в пути/i)).toBeInTheDocument()
    // …but the parcel leaves the sender's hands, so declaring that is not.
    expect(screen.queryByText(/declare handover|Заявить передачу/i)).not.toBeInTheDocument()
  })

  it('offers nothing to somebody who is not a party', () => {
    const { container } = renderWithProviders(
      <CardActions dealId="d1" myRole={null} onDone={() => {}} />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('sends the chosen kind with its payload', async () => {
    renderWithProviders(<CardActions dealId="d1" myRole="sender" onDone={() => {}} />)
    fireEvent.click(screen.getByText(/report an issue|Сообщить о проблеме/i))

    const select = screen.getByRole('combobox')
    fireEvent.change(select, { target: { value: 'delay' } })
    fireEvent.click(screen.getByText(/^send$|^Отправить$/i))

    await waitFor(() =>
      expect(raiseCard).toHaveBeenCalledWith(
        'd1',
        'issue.reported',
        { category: 'delay' },
        undefined,
      ),
    )
  })
})

// ── the declaration itself ────────────────────────────────────────────────

describe('cardForms', () => {
  it('mirrors the server on who raises what', () => {
    const senderKinds = formsForRole('sender').map((f) => f.kind)
    expect(senderKinds).toContain('handoff.declared')
    expect(senderKinds).toContain('payment.declared')
    expect(senderKinds).not.toContain('transit.update')
    expect(senderKinds).not.toContain('delivery.declared')
  })

  it('gives the recipient only what concerns their end', () => {
    const kinds = formsForRole('recipient').map((f) => f.kind)
    expect(kinds).toEqual(['dropoff.proposed', 'issue.reported'])
  })

  it('drops empty optionals so the server default applies', () => {
    // Sending `""` or `NaN` would overwrite a default with a value nobody typed.
    const spec = specForKind('pickup.proposed')!
    expect(buildPayload(spec, { method: 'courier', city: '', window_minutes: '' })).toEqual({
      method: 'courier',
    })
  })

  it('always sends booleans, because false is an answer', () => {
    const spec = specForKind('handover.conditions')!
    const out = buildPayload(spec, { fragile: false })
    expect(out.fragile).toBe(false)
    expect(out.open_on_handover).toBe(false)
  })

  it('coerces numbers and datetimes rather than passing strings through', () => {
    const spec = specForKind('payment.declared')!
    const out = buildPayload(spec, { amount: '120.5', currency: 'USD', method: 'cash' })
    expect(out.amount).toBe(120.5)

    const transit = specForKind('transit.update')!
    const t = buildPayload(transit, { stage: 'departed', eta: '2026-09-01T10:00' })
    expect(String(t.eta)).toMatch(/^2026-09-01T/)
  })

  it('ignores a number that is not one', () => {
    const spec = specForKind('payment.declared')!
    expect(buildPayload(spec, { amount: 'lots' })).toEqual({})
  })
})
