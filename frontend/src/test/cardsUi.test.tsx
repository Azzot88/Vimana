import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import TermsCard from '../components/TermsCard'
import DealCard from '../components/DealCard'
import CardActions from '../components/CardActions'
import DealStages from '../components/DealStages'
import MeetingNote, { meetingOf } from '../components/MeetingNote'
import type { VaultMessage } from '../api/dealvault'
import type { DealStatus } from '../api/deals'
import type { DealRole } from '../lib/cardForms'
import type { Terms } from '../api/terms'
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
  return { ...actual, raiseCard: vi.fn(), raiseCardWithFiles: vi.fn() }
})

import { ackCard, messagesSignature, uploadAttachment } from '../api/dealvault'
import { raiseCard, raiseCardWithFiles } from '../api/terms'

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
  vi.mocked(raiseCardWithFiles).mockReset().mockResolvedValue({} as never)
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

  it('says when an unanswered cancellation stops waiting', () => {
    // T3.11.27 — the one field on this card that changes what happens if
    // nobody touches the screen, so it is a sentence rather than one more
    // `key: value` row printing a raw ISO string.
    renderWithProviders(
      <DealCard
        msg={msg({
          card_kind: 'cancel.requested',
          card_state: 'pending',
          requires_ack_by: 'carrier',
          card_payload: {
            costs_borne_by: 'split',
            expires_at: '2026-09-09T10:00:00Z',
          },
        })}
        dealId="d1"
        myRole="carrier"
        mine={false}
        onChanged={() => {}}
      />,
    )
    expect(
      screen.getByText(/cancels itself|отменится сама/i),
    ).toBeInTheDocument()
    expect(screen.queryByText('2026-09-09T10:00:00Z')).not.toBeInTheDocument()
  })

  it('drops the deadline once the card is answered', () => {
    renderWithProviders(
      <DealCard
        msg={msg({
          card_kind: 'cancel.requested',
          card_state: 'accepted',
          requires_ack_by: null,
          card_payload: {
            costs_borne_by: 'split',
            expires_at: '2026-09-09T10:00:00Z',
          },
        })}
        dealId="d1"
        myRole="carrier"
        mine={false}
        onChanged={() => {}}
      />,
    )
    expect(
      screen.queryByText(/cancels itself|отменится сама/i),
    ).not.toBeInTheDocument()
  })
})

// ── raising a card ────────────────────────────────────────────────────────

describe('CardActions', () => {
  it('offers only what this role may actually raise', () => {
    renderWithProviders(<CardActions dealId="d1" myRole="carrier" onDone={() => {}} />)
    // The carrier moves the cargo, so transit updates are theirs…
    expect(screen.getByText(/transit update|Статус в пути/i)).toBeInTheDocument()
    /* …and since T_UX.28 п.5 the handover is theirs to record as well: one
       card, raised by whichever side is holding the parcel. What a carrier
       still may not do is speak for the sender's own cargo photograph. */
    expect(
      screen.getByText(/record the handover|Зафиксировать передачу/i),
    ).toBeInTheDocument()
    expect(
      screen.queryByText(/what I am sending|Вот что я отправляю/i),
    ).not.toBeInTheDocument()
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
    // T3.12.07 — the handover in hand is declared by either side; the sender is
    // the receiving side when there is no separate recipient.
    expect(senderKinds).toContain('delivery.declared')
  })

  it('gives the recipient only what concerns their end', () => {
    // T3.11.27 — `payment.declared` joined this list because a deal can be
    // «получатель платит на месте». The catalogue is as far as the role can
    // take it; which of the two parties actually owes the money is written in
    // the agreement, and `DealStages` reads `payer` to drop the button for the
    // one who owes nothing.
    const kinds = formsForRole('recipient').map((f) => f.kind)
    // T3.12.07 — `delivery.declared` too: the recipient says what they received.
    expect(kinds).toEqual([
      'dropoff.proposed',
      'delivery.declared',
      // T3.12.08 — and closes a posted deal: «получено как должно».
      'received.as_expected',
      'payment.declared',
      'issue.reported',
    ])
    // Still nothing about the cargo itself: the recipient neither hands it over
    // nor carries it.
    expect(kinds).not.toContain('handoff.declared')
    expect(kinds).not.toContain('transit.update')
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

// ── the stage panel ───────────────────────────────────────────────────────

describe('DealStages', () => {
  const panel = (over: { status?: DealStatus; myRole?: DealRole } = {}) => (
    <DealStages
      dealId="d1"
      status={over.status ?? 'delivered'}
      myRole={over.myRole ?? 'sender'}
      terms={null}
      deal={null}
      messages={[]}
      onDone={() => {}}
    />
  )

  it('names the arbiter when the parcel is handed over and unpaid', () => {
    // T3.11.27 — «Отдано, но не оплачено — доступно "Пригласить арбитра"».
    // Somebody in this position is already unsure whether they are allowed to
    // complain, so the panel says it rather than hiding it behind «ещё».
    renderWithProviders(panel({ status: 'delivered' }))
    expect(
      screen.getByText(/invite an arbiter|Позовите арбитра/i),
    ).toBeInTheDocument()
    expect(screen.getByText(/open dispute|Открыть спор/i)).toBeInTheDocument()
  })

  it('does not put the arbiter in the way while the terms are being agreed', () => {
    renderWithProviders(panel({ status: 'draft' }))
    expect(
      screen.queryByText(/invite an arbiter|Позовите арбитра/i),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByText(/open dispute|Открыть спор/i),
    ).not.toBeInTheDocument()
  })

  it('offers no closing shortcut once the parcel changed hands in person', () => {
    // The pair «получил» + «рассчитался» is what closes such a deal; a second
    // route past it would let one side close without the other's press.
    renderWithProviders(panel({ status: 'delivered' }))
    expect(
      screen.queryByText(/close the deal|Закрыть сделку/i),
    ).not.toBeInTheDocument()
  })

  it('has no shortcut on the postal stretch either, since 2026-09-12', () => {
    /* It was kept there on the honest argument that a carrier who has posted
       the parcel should not wait on a post office. What it actually did was end
       deals past «Оплата произведена» and past anybody confirming receipt — the
       run the owner walked closed exactly that way. The postal stretch now closes
       through the same pair as every other deal. */
    renderWithProviders(panel({ status: 'posted' }))
    expect(
      screen.queryByText(/close the deal|Закрыть сделку/i),
    ).not.toBeInTheDocument()
  })

  it('says nothing is left to do on a cancelled deal', () => {
    renderWithProviders(panel({ status: 'cancelled' }))
    expect(screen.queryByText(/^more$|^ещё$/i)).not.toBeInTheDocument()
  })
})

// ── T3.11.27 · the photo travels with the card ────────────────────────────

describe('CardActions with evidence', () => {
  it('sends the declaration and its photographs as one request', async () => {
    /* Two defects, one rule. The photograph used to go up as its own chat
       message, so the card never got the evidence its spec requires; then it
       went up as a second request, so a refused upload left a card nobody could
       confirm in a chain that cannot take it back. «Без фото карточка в чат
       добавляться не должна» (owner, 2026-09-12) — so it is one request, and
       the server writes nothing until every file is accepted. */
    renderWithProviders(<CardActions dealId="d1" myRole="sender" onDone={() => {}} />)
    fireEvent.click(screen.getByText(/record the handover|Зафиксировать передачу/i))

    const front = new File(['x'], 'front.png', { type: 'image/png' })
    const inside = new File(['y'], 'inside.png', { type: 'image/png' })
    const input = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement
    fireEvent.change(input, { target: { files: [front, inside] } })
    fireEvent.click(screen.getByText(/^send$|^Отправить$/i))

    await waitFor(() =>
      expect(raiseCardWithFiles).toHaveBeenCalledWith(
        'd1',
        'handoff.declared',
        [front, inside],
        {},
        undefined,
        // T_UX.28 п.4 — the selfie pile, empty here and still its own argument:
        // it travels in its own part so the server can file it under its own
        // kind.
        [],
      ),
    )
    // Never the plain endpoint for a card that stands on evidence.
    expect(raiseCard).not.toHaveBeenCalled()
  })

  it('takes several photographs, because one side of a box proves nothing', () => {
    renderWithProviders(<CardActions dealId="d1" myRole="sender" onDone={() => {}} />)
    fireEvent.click(screen.getByText(/record the handover|Зафиксировать передачу/i))
    const input = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement
    expect(input.multiple).toBe(true)
  })

  it('says what to photograph, not just that a photo is needed', () => {
    // «Надо открыть посылку и снять содержимое» (owner, 2026-09-12). The one
    // line on this form an arbiter will later wish somebody had read.
    renderWithProviders(<CardActions dealId="d1" myRole="sender" onDone={() => {}} />)
    fireEvent.click(screen.getByText(/record the handover|Зафиксировать передачу/i))
    expect(
      screen.getByText(/open the parcel|Откройте посылку/i),
    ).toBeInTheDocument()
  })

  it('no longer asks how many parcels there are', () => {
    // «Количество мест сколько передано надо убрать. Основное это фотография.»
    // A number somebody types about their own parcel proves nothing an arbiter
    // can use, and it asked for it in a doorway with one hand free.
    renderWithProviders(<CardActions dealId="d1" myRole="sender" onDone={() => {}} />)
    fireEvent.click(screen.getByText(/record the handover|Зафиксировать передачу/i))
    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument()
  })

  it('refuses to raise a declaration with no evidence', async () => {
    /* Refused before anything is sent. The server would refuse it too — this is
       the same rule stated where it costs nothing. */
    renderWithProviders(<CardActions dealId="d1" myRole="sender" onDone={() => {}} />)
    fireEvent.click(screen.getByText(/record the handover|Зафиксировать передачу/i))
    fireEvent.click(screen.getByText(/^send$|^Отправить$/i))

    await waitFor(() =>
      expect(
        screen.getByText(/attach the photo|Приложите фото/i),
      ).toBeInTheDocument(),
    )
    expect(raiseCard).not.toHaveBeenCalled()
    expect(raiseCardWithFiles).not.toHaveBeenCalled()
  })

  it('gives both sides the same handover card', () => {
    /* T_UX.28 п.5 (owner, 2026-09-19): «фотографии передачи делает любой
       участник… если фото добавил один из участников, дублировать тот же
       функционал у второго не нужно.»

       This replaces the pair: the carrier used to have `handoff.received` and
       the sender `handoff.declared`, both requiring a photograph of the same
       moment. The retired kind is gone from the forms — it stays in the
       catalogue only so old deals can still be read. */
    const carrierKinds = formsForRole('carrier').map((f) => f.kind)
    const senderKinds = formsForRole('sender').map((f) => f.kind)
    expect(carrierKinds).toContain('handoff.declared')
    expect(senderKinds).toContain('handoff.declared')
    expect(carrierKinds).not.toContain('handoff.received')
    expect(senderKinds).not.toContain('handoff.received')
  })
})

// ── T3.11.27 · whose turn it is, and the stage nobody could act on ────────

describe('DealStages · the late stages', () => {
  const panel = (over: { status?: DealStatus; myRole?: DealRole } = {}) => (
    <DealStages
      dealId="d1"
      status={over.status ?? 'delivered'}
      myRole={over.myRole ?? 'sender'}
      terms={null}
      deal={null}
      messages={[]}
      onDone={() => {}}
    />
  )

  it('offers the money card once the parcel has arrived', () => {
    /* The bug behind «Нет кнопки Сколько денег получено… Но сделка закрылась»:
       `delivery` and `payment` share their statuses on purpose, and the panel
       read only the first of them — whose kinds are empty. Nothing to press at
       `delivered`, so the only way out was the one-press close. */
    renderWithProviders(panel({ status: 'delivered', myRole: 'sender' }))
    expect(
      screen.getByText(/payment made|Оплата произведена/i),
    ).toBeInTheDocument()
  })

  it('offers it on the postal stretch too', () => {
    renderWithProviders(panel({ status: 'posted', myRole: 'sender' }))
    expect(
      screen.getByText(/payment made|Оплата произведена/i),
    ).toBeInTheDocument()
  })

  it('lets the receiving side close a posted deal, paid or not', () => {
    // T3.12.08 — «получено как должно», at `posted` and at `confirmed`.
    renderWithProviders(panel({ status: 'posted', myRole: 'sender' }))
    expect(
      screen.getByText(/received as expected|Получено как должно/i),
    ).toBeInTheDocument()
  })

  it('keeps it for a paid posted deal waiting for the parcel', () => {
    renderWithProviders(panel({ status: 'confirmed', myRole: 'sender' }))
    expect(
      screen.getByText(/received as expected|Получено как должно/i),
    ).toBeInTheDocument()
  })

  it('does not offer it for a parcel that was not posted', () => {
    renderWithProviders(panel({ status: 'delivered', myRole: 'sender' }))
    expect(
      screen.queryByText(/received as expected|Получено как должно/i),
    ).not.toBeInTheDocument()
  })

  it('does not offer it to the side that owes nothing', () => {
    // `payer` defaults to the sender, and the server answers the carrier 403.
    renderWithProviders(panel({ status: 'delivered', myRole: 'carrier' }))
    expect(
      screen.queryByText(/payment made|Оплата произведена/i),
    ).not.toBeInTheDocument()
  })

  it('says whose turn it is instead of drawing a blank', () => {
    /* Two different silences used to look identical: «нечего нажимать» and
       «сейчас не твой ход». The second one is now a sentence. */
    renderWithProviders(panel({ status: 'delivered', myRole: 'carrier' }))
    expect(
      screen.getByText(/other side's turn|ход второй стороны/i),
    ).toBeInTheDocument()
  })

  it('says nothing of the kind when this role does have a step', () => {
    renderWithProviders(panel({ status: 'accepted', myRole: 'sender' }))
    expect(
      screen.queryByText(/other side's turn|ход второй стороны/i),
    ).not.toBeInTheDocument()
    expect(
      screen.getByText(/record the handover|Зафиксировать передачу/i),
    ).toBeInTheDocument()
  })

  it('keeps quiet at a stage where nobody acts', () => {
    // At `closed` the silence is correct, and «ждём вторую сторону» would be a
    // lie rather than a hint.
    renderWithProviders(panel({ status: 'closed', myRole: 'sender' }))
    expect(
      screen.queryByText(/other side's turn|ход второй стороны/i),
    ).not.toBeInTheDocument()
  })

  it('gives the carrier the same handover card as the sender', () => {
    /* T_UX.28 п.5 — one card, raised by whoever is holding the parcel. The
       carrier used to have a card of their own («Получил посылку») requiring a
       photograph of the same moment the sender was photographing. */
    renderWithProviders(panel({ status: 'accepted', myRole: 'carrier' }))
    expect(
      screen.getByText(/record the handover|Зафиксировать передачу/i),
    ).toBeInTheDocument()
  })
})

// ── T3.11.27 · the screen notices the other side ──────────────────────────

describe('messagesSignature', () => {
  /* The deal screen polls every ten seconds. What it compares decides whether
     the poll is useful at all — and every one of these three cases was a real
     symptom: «статус не сменился ни у кого», «карточка так и висит в ожидании»,
     «фото загрузилось, но у второго не появилось». */
  const m = (over: Partial<VaultMessage>): VaultMessage => msg(over)

  it('is unchanged when nothing happened, so the list is kept', () => {
    // Kept, not replaced: an equal array re-runs every effect that depends on
    // it, and one of those scrolls somebody's history to the bottom.
    const a = [m({ id: '1' }), m({ id: '2' })]
    const b = [m({ id: '1' }), m({ id: '2' })]
    expect(messagesSignature(a)).toBe(messagesSignature(b))
  })

  it('changes when the other side answers a card already on screen', () => {
    const pending = [m({ id: '1', card_state: 'pending' })]
    const answered = [m({ id: '1', card_state: 'accepted' })]
    expect(messagesSignature(pending)).not.toBe(messagesSignature(answered))
  })

  it('changes when a photo lands on a message that is otherwise untouched', () => {
    const bare = [m({ id: '1' })]
    const withPhoto = [
      m({
        id: '1',
        attachments: [
          {
            id: 'a1',
            message_id: '1',
            r2_key: 'k',
            file_hash: 'h',
            ipfs_cid: null,
            kind: 'handoff_photo',
            url: null,
            created_at: '2026-09-12T00:00:00Z',
          },
        ],
      }),
    ]
    expect(messagesSignature(bare)).not.toBe(messagesSignature(withPhoto))
  })

  it('changes when a message arrives', () => {
    expect(messagesSignature([m({ id: '1' })])).not.toBe(
      messagesSignature([m({ id: '1' }), m({ id: '2' })]),
    )
  })
})

// ── T3.11.27 · the evidence, and the button that has been pressed ─────────

describe('DealCard · what it shows', () => {
  it('leaves out a field nobody filled', () => {
    // An empty label reads as a field somebody failed to answer, not as one
    // they were never asked.
    renderWithProviders(
      <DealCard
        msg={msg({
          card_kind: 'handoff.declared',
          card_state: 'pending',
          requires_ack_by: 'carrier',
          card_payload: { parcel_count: 2, postal_service: '   ' },
          attachments: [
            {
              id: 'a1',
              message_id: 'm1',
              r2_key: 'k',
              file_hash: 'abcdef0123456789ff',
              ipfs_cid: null,
              kind: 'handoff_photo',
              url: 'https://example.test/p.png',
              created_at: '2026-09-12T00:00:00Z',
            },
          ],
        })}
        dealId="d1"
        myRole="carrier"
        mine={false}
        onChanged={() => {}}
      />,
    )
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(
      screen.queryByText(/postal service|Служба доставки/i),
    ).not.toBeInTheDocument()
  })

  it('carries the photo, its kind and its hash — the chat draws none of them now', () => {
    const onPreview = vi.fn()
    renderWithProviders(
      <DealCard
        msg={msg({
          card_kind: 'handoff.declared',
          card_state: 'pending',
          requires_ack_by: 'carrier',
          card_payload: { parcel_count: 1 },
          attachments: [
            {
              id: 'a1',
              message_id: 'm1',
              r2_key: 'k',
              file_hash: 'abcdef0123456789ff',
              ipfs_cid: null,
              kind: 'handoff_photo',
              url: 'https://example.test/p.png',
              created_at: '2026-09-12T00:00:00Z',
            },
          ],
        })}
        dealId="d1"
        myRole="carrier"
        mine={false}
        onChanged={() => {}}
        onPreview={onPreview}
      />,
    )
    expect(screen.getByText(/sha256:abcdef0123456789/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /full screen|весь экран/i }))
    expect(onPreview).toHaveBeenCalledWith(
      expect.objectContaining({ url: 'https://example.test/p.png' }),
    )
  })
})

describe('DealStages · a card already raised', () => {
  const panel = (over: {
    status?: DealStatus
    myRole?: DealRole
    messages?: VaultMessage[]
  }) => (
    <DealStages
      dealId="d1"
      status={over.status ?? 'accepted'}
      myRole={over.myRole ?? 'sender'}
      terms={null}
      deal={null}
      messages={over.messages ?? []}
      onDone={() => {}}
    />
  )

  it('takes the button away the moment the declaration is standing', () => {
    /* «После того как нажата кнопка Передал перевозчику она должна пропадать
       сразу» (owner, 2026-09-12). It used to hang around until the status moved
       — which happens only when the other side confirms — so the same handover
       could be declared twice, and the chain would hold two contradictory
       accounts of one act. */
    renderWithProviders(
      panel({
        messages: [
          msg({
            card_kind: 'handoff.declared',
            card_state: 'pending',
            requires_ack_by: 'carrier',
          }),
        ],
      }),
    )
    expect(
      screen.queryByText(/record the handover|Зафиксировать передачу/i),
    ).not.toBeInTheDocument()
    /* And **not** «сейчас ход второй стороны»: moving the meeting is still
       this person's to press, so the stage has not gone quiet — it has one
       fewer button. The two silences this panel distinguishes are «нечего
       нажимать» and «не твой ход»; a standing declaration is neither. */
    /* The meeting button, under whichever of its two names applies: since
       T_UX.28 it reads «Назначить встречу» until one is arranged and «Перенести»
       after. Nothing is arranged in this fixture, so it is the first — and the
       assertion is about the button being there, not about its wording. */
    expect(
      screen.getByText(/set the meeting|move the meeting|Назначить встречу|Перенести встречу/i),
    ).toBeInTheDocument()
    expect(
      screen.queryByText(/other side's turn|ход второй стороны/i),
    ).not.toBeInTheDocument()
  })

  it('says whose turn it is once every card of theirs is standing', () => {
    /* Both of the carrier's cards at this stage are awaiting an answer — the
       receipt they declared and the meeting they asked to move. Now there is
       genuinely nothing to press, and that is when the line belongs. */
    renderWithProviders(
      panel({
        myRole: 'carrier',
        messages: [
          msg({
            card_kind: 'handoff.declared',
            card_state: 'pending',
            requires_ack_by: 'sender',
          }),
          msg({
            id: 'm2',
            card_kind: 'pickup.proposed',
            card_state: 'pending',
            requires_ack_by: 'sender',
          }),
        ],
      }),
    )
    expect(
      screen.queryByText(/record the handover|Зафиксировать передачу/i),
    ).not.toBeInTheDocument()
    expect(
      screen.getByText(/other side's turn|ход второй стороны/i),
    ).toBeInTheDocument()
  })

  it('gives it back when the other side refuses', () => {
    // The rollback of one step, and it needs no state of its own: the poll
    // brings the refusal, and the button returns with it.
    renderWithProviders(
      panel({
        messages: [
          msg({ card_kind: 'handoff.declared', card_state: 'declined' }),
        ],
      }),
    )
    expect(
      screen.getByText(/record the handover|Зафиксировать передачу/i),
    ).toBeInTheDocument()
  })

  it('ignores a standing card that belongs to the other side', () => {
    // A pending `transit.update` is the carrier's business; it must not remove
    // the sender's own handover button.
    renderWithProviders(
      panel({
        messages: [msg({ card_kind: 'transit.update', card_state: 'pending' })],
      }),
    )
    expect(
      screen.getByText(/record the handover|Зафиксировать передачу/i),
    ).toBeInTheDocument()
  })
})

// ── T3.11.27 · landing is its own step ────────────────────────────────────

describe('the ladder after the flight lands', () => {
  const panel = (messages: VaultMessage[]) => (
    <DealStages
      dealId="d1"
      status="in_transit"
      myRole="carrier"
      terms={null}
      deal={null}
      messages={messages}
      onDone={() => {}}
    />
  )

  it('stands on «в пути» until somebody says it landed', () => {
    renderWithProviders(panel([]))
    expect(screen.getByRole('heading', { name: /in transit|В пути/i })).toBeInTheDocument()
  })

  it('moves to «прилетел» on the carrier’s own update', () => {
    /* «Разделить статусы Вылетел В Пути и Прилетел на два экрана» (owner,
       2026-09-12). One rung covered a flight, a landing and a day of waiting
       for a call — three situations that look the same on the ladder and feel
       nothing alike to the person waiting. */
    renderWithProviders(
      panel([
        msg({
          card_kind: 'transit.update',
          card_state: 'accepted',
          card_payload: { stage: 'arrived' },
        }),
      ]),
    )
    expect(screen.getByRole('heading', { name: /landed|Прилетел/i })).toBeInTheDocument()
  })

  it('is not moved by a departure', () => {
    renderWithProviders(
      panel([
        msg({
          card_kind: 'transit.update',
          card_state: 'accepted',
          card_payload: { stage: 'departed' },
        }),
      ]),
    )
    expect(screen.getByRole('heading', { name: /in transit|В пути/i })).toBeInTheDocument()
  })
})

// ── T3.11.27 · where you meet, and what to do there ───────────────────────

describe('MeetingNote', () => {
  const NOW = Date.parse('2026-09-13T12:00:00Z')
  const at = (hours: number) => new Date(NOW + hours * 3600_000).toISOString()

  const terms = (over: Record<string, unknown> = {}): Terms =>
    ({
      id: 't1',
      deal_id: 'd1',
      card_kind: 'terms.agreed',
      card_state: 'accepted',
      requires_ack_by: null,
      supersedes_id: null,
      payload: {
        handover_place: 'Dubai Mall, by the fountain',
        handover_method: 'in_person',
        ...over,
      },
      description: null,
      created_at: '2026-09-13T10:00:00Z',
    }) as Terms

  it('reads the arrangement out of the agreement', () => {
    expect(meetingOf(terms(), [], 'handover')).toEqual({
      place: 'Dubai Mall, by the fountain',
      method: 'in_person',
      at: undefined,
    })
  })

  it('lets an accepted meeting card move it', () => {
    // The card is how a meeting is moved (T3.11.27), so it outranks the version
    // of the agreement that was written before anybody moved anything.
    const moved = meetingOf(
      terms(),
      [
        msg({
          card_kind: 'pickup.proposed',
          card_state: 'accepted',
          card_payload: { method: 'in_person', city: 'Marina', at: at(2) },
        }),
      ],
      'handover',
    )
    expect(moved.place).toBe('Marina')
    expect(moved.at).toBe(at(2))
  })

  it('ignores a proposal nobody has answered', () => {
    /* A pending card is one side's request. Printing it as «где вы
       встречаетесь» would tell two people they agreed on something one of them
       has not read. */
    const still = meetingOf(
      terms(),
      [
        msg({
          card_kind: 'pickup.proposed',
          card_state: 'pending',
          card_payload: { method: 'courier', city: 'Marina' },
        }),
      ],
      'handover',
    )
    expect(still.place).toBe('Dubai Mall, by the fountain')
  })

  it('shows a standing proposal where nothing has been arranged', () => {
    /* T_UX.28 п.9 — the other half of the same rule. Nothing agreed and
       nothing in the terms: the card is the only thing that knows a place was
       named at all, and silence here leaves the person who proposed it with no
       trace of their own request. */
    renderWithProviders(
      <MeetingNote
        terms={null}
        messages={[
          msg({
            card_kind: 'pickup.proposed',
            card_state: 'pending',
            card_payload: { method: 'in_person', city: 'Marina', at: at(2) },
          }),
        ]}
        stage="handover"
        myRole="sender"
        now={NOW}
      />,
    )
    expect(screen.getByText(/Marina/)).toBeInTheDocument()
    // And said to be a question, not an arrangement.
    expect(
      screen.getByText(/^proposed$|^предложено$/i),
    ).toBeInTheDocument()
  })

  it('says how long is left, not only when it is', () => {
    // «Указатель сколько часов до неё осталось» (owner, 2026-09-12). A date
    // agreed three days ago reads as an arrangement; «через 2 часа» reads as
    // something to leave for now.
    renderWithProviders(
      <MeetingNote
        terms={terms({ handover_at: at(2) })}
        messages={[]}
        stage="handover"
        myRole="sender"
        now={NOW}
      />,
    )
    expect(screen.getByText(/in 2 hours|через 2 часа/i)).toBeInTheDocument()
  })

  it('gives the carrier the checks, and the sender none of them', () => {
    /* The sender does not weigh their own parcel or compare it with their own
       description. The same lines for both would make this a wall of advice,
       and a wall of advice is read by nobody. */
    const { unmount } = renderWithProviders(
      <MeetingNote
        terms={terms()}
        messages={[]}
        stage="handover"
        myRole="carrier"
        now={NOW}
      />,
    )
    expect(screen.getByText(/weigh the parcel|Взвесьте посылку/i)).toBeInTheDocument()
    expect(
      screen.getByText(/compare the contents|Сверьте содержимое/i),
    ).toBeInTheDocument()
    unmount()

    renderWithProviders(
      <MeetingNote
        terms={terms()}
        messages={[]}
        stage="handover"
        myRole="sender"
        now={NOW}
      />,
    )
    expect(
      screen.queryByText(/weigh the parcel|Взвесьте посылку/i),
    ).not.toBeInTheDocument()
  })

  it('draws nothing when there is no arrangement to describe', () => {
    const { container } = renderWithProviders(
      <MeetingNote terms={null} messages={[]} stage="handover" myRole="sender" />,
    )
    expect(container).toBeEmptyDOMElement()
  })
})

// ── T_UX.29 · the flight goes one way, and the panel says which ───────────

describe('the status form on the flight', () => {
  const flight = (messages: VaultMessage[], myRole: DealRole = 'carrier') => (
    <DealStages
      dealId="d1"
      status="in_transit"
      myRole={myRole}
      terms={null}
      deal={null}
      messages={messages}
      onDone={() => {}}
    />
  )
  const update = (stage: string): VaultMessage =>
    msg({
      id: `t-${stage}`,
      card_kind: 'transit.update',
      card_state: 'accepted',
      card_payload: { stage },
    })

  it('stands open rather than behind a button', () => {
    /* T_UX.29 п.1 (owner, 2026-09-20): «Статус "В пути" в Поле изменения
       статуса должен быть виден сразу, а не за кнопкой. Статус "В пути" это то
       же самое что и этап "В пути".» The form's own field is on the screen
       with nothing pressed. */
    renderWithProviders(flight([]))
    expect(screen.getByText(/^Stage$|^Этап$/)).toBeInTheDocument()
  })

  it('stays open while its own card is waiting for an answer', () => {
    /* A transit card waits on «Принято» and the journey does not: a carrier who
       declared a delay still has to declare the landing an hour later. Standing
       on its own pending card is how the form vanished from the stage named
       after it. */
    renderWithProviders(
      flight([
        msg({
          id: 'p1',
          card_kind: 'transit.update',
          card_state: 'pending',
          requires_ack_by: 'sender',
          card_payload: { stage: 'delayed' },
        }),
      ]),
    )
    expect(screen.getByText(/^Stage$|^Этап$/)).toBeInTheDocument()
  })

  it('offers nothing behind the furthest status declared', () => {
    renderWithProviders(flight([update('departed'), update('arrived')]))
    // Drawn as a record — visible, with nothing to press.
    expect(screen.getByText(/^Departed$|^Вылетел$/)).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /^Departed$|^Вылетел$/ }),
    ).not.toBeInTheDocument()
    // The conditions keep their freedom: customs happens after a landing as
    // readily as before one.
    expect(
      screen.getByRole('button', { name: /^Customs$|^Таможня$/ }),
    ).toBeInTheDocument()
  })

  it('marks the live rung of the progress panel for a reader', () => {
    renderWithProviders(flight([update('departed')]))
    const live = document.querySelector('[aria-current="step"]')
    expect(live?.textContent).toMatch(/in transit|В пути/i)
  })
})

describe('the far side of the flight', () => {
  const flight = (messages: VaultMessage[], myRole: DealRole = 'carrier') => (
    <DealStages
      dealId="d1"
      status="in_transit"
      myRole={myRole}
      terms={null}
      deal={null}
      messages={messages}
      onDone={() => {}}
    />
  )
  const update = (stage: string): VaultMessage =>
    msg({
      id: `t-${stage}`,
      card_kind: 'transit.update',
      card_state: 'accepted',
      card_payload: { stage },
    })

  it('keeps the arrival’s actions away from a parcel in the air', () => {
    /* T_UX.29 п.3 (owner, 2026-09-20): «пока посылка не прилетела, не должно
       показываться статусов "Отправлено по почте" и "Передано в доставку"».
       `transit` and `arrived` share the status `in_transit`, and the union
       «every stage standing on the current status» put the whole arrival over a
       flight still in the air. */
    /* Anchored on purpose: this stage's own hint ends «…posted by mail or
       handed to delivery», so a loose match finds the sentence explaining the
       stage rather than a control that should not be on it. What is being
       asserted is the **action**, and an action is a button or a form's
       heading — both of which carry the label and nothing else. */
    renderWithProviders(flight([update('departed')]))
    expect(
      screen.queryByText(/^posted by mail$|^отправлено по почте$/i),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByText(/^handed to delivery$|^передано в доставку$/i),
    ).not.toBeInTheDocument()
  })

  it('offers them once the flight is down', () => {
    renderWithProviders(flight([update('arrived')]))
    expect(
      screen.getByText(/^posted by mail$|^отправлено по почте$/i),
    ).toBeInTheDocument()
  })

  it('lets only the carrier name the handover method first', () => {
    /* T_UX.29 п.4 — «должен быть доступен для настройки только Перевозчику,
       Получатель либо соглашается, либо предлагает изменения». */
    renderWithProviders(flight([update('arrived')], 'recipient'))
    expect(
      screen.queryByText(/delivery method|Способ передачи/i),
    ).not.toBeInTheDocument()
  })

  it('gives it back to the recipient once it has been named', () => {
    /* The second half of the rule: «либо соглашается, либо предлагает
       изменения». An arrangement standing is something to disagree with, and
       the caption says so — «Перенести вручение», not «Способ передачи». */
    renderWithProviders(
      flight(
        [
          update('arrived'),
          msg({
            id: 'drop1',
            card_kind: 'dropoff.proposed',
            card_state: 'accepted',
            card_payload: { method: 'in_person', city: 'Queens' },
          }),
        ],
        'recipient',
      ),
    )
    expect(
      screen.getByText(/move the delivery|Перенести вручение/i),
    ).toBeInTheDocument()
  })
})

// ── T_UX.29 pt.2 · where it is now, and what the next act is called ───────

describe('the panel after a status that is not a rung', () => {
  const flight = (messages: VaultMessage[], myRole: DealRole = 'recipient') => (
    <DealStages
      dealId="d1"
      status="in_transit"
      myRole={myRole}
      terms={null}
      deal={null}
      messages={messages}
      onDone={() => {}}
    />
  )
  const update = (stage: string, id = `t-${stage}`): VaultMessage =>
    msg({
      id,
      card_kind: 'transit.update',
      card_state: 'accepted',
      card_payload: { stage },
    })

  it('says where the parcel is now, not only in the chat', () => {
    /* T_UX.29 pt.2 п.1 (owner, 2026-09-20): «После смены статуса "Прилетел" на
       "Таможня" окно не обновилось и кнопки остались в том же наборе.» The news
       went into the chat and the left-hand column stood as it was. */
    renderWithProviders(flight([update('arrived'), update('customs')]))
    expect(screen.getByText(/^Now: Customs|^Сейчас: Таможня/)).toBeInTheDocument()
  })

  it('tells the recipient what storage means for them', () => {
    /* T_UX.29 pt.2 п.3 — «Статус хранение должен показывать получателю, что
       можно планировать забор посылки. Он сигнализирует, что таможня пройдена
       и можно встречаться.» */
    renderWithProviders(flight([update('arrived'), update('storage')]))
    expect(
      screen.getByText(/arrange the meeting|можно договариваться о встрече/i),
    ).toBeInTheDocument()
  })

  it('does not repeat the rung it is standing on', () => {
    // «Сейчас: Прилетел» under a heading reading «Прилетел» informs nobody.
    renderWithProviders(flight([update('arrived')]))
    expect(screen.queryByText(/^Now: |^Сейчас: /)).not.toBeInTheDocument()
  })
})

describe('an arrangement that already stands', () => {
  const agreed = (over: Record<string, unknown> = {}): Terms =>
    ({
      id: 't1',
      deal_id: 'd1',
      card_kind: 'terms.agreed',
      card_state: 'accepted',
      requires_ack_by: null,
      supersedes_id: null,
      payload: { delivery_method: 'in_person', ...over },
      description: null,
      created_at: '2026-09-20T10:00:00Z',
    }) as Terms

  const landed = msg({
    id: 't-arrived',
    card_kind: 'transit.update',
    card_state: 'accepted',
    card_payload: { stage: 'arrived' },
  })
  const settled = msg({
    id: 'drop-ok',
    card_kind: 'dropoff.proposed',
    card_state: 'accepted',
    card_payload: { method: 'in_person' },
  })

  const panel = (messages: VaultMessage[], terms: Terms | null = agreed()) => (
    <DealStages
      dealId="d1"
      status="in_transit"
      myRole="recipient"
      terms={terms}
      deal={null}
      messages={messages}
      onDone={() => {}}
    />
  )

  it('stops calling it «Способ передачи» once a card has been answered', () => {
    /* T_UX.29 pt.2 п.2 (owner, 2026-09-20): «Всё ещё предлагается выбрать
       способ передачи, хотя он уже назначен — и написано, что условия уже
       согласованы.» The caption was decided by place and time alone, so an
       accepted card naming only the method left the section reading «unset». */
    renderWithProviders(panel([landed, settled]))
    expect(
      screen.queryByText(/delivery method|Способ передачи/i),
    ).not.toBeInTheDocument()
    expect(
      screen.getByText(/move the delivery|Перенести вручение/i),
    ).toBeInTheDocument()
  })

  it('does not unfold itself over an arrangement the two of them made', () => {
    // The stage opens with the step that is actually next; changing a standing
    // arrangement stays one press away.
    renderWithProviders(panel([landed, settled]))
    // The open form is the handover; the meeting is a button under it.
    expect(screen.getByText(/^Handed over$|^Вручено$/)).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /move the delivery|Перенести вручение/i }),
    ).toBeInTheDocument()
  })

  it('calls a hand-to-hand delivery «Вручено», not «Передано в доставку»', () => {
    /* T_UX.29 pt.2 п.4 — one card ends the carriage two ways, and the agreed
       method says which. «Передано в доставку» over a meeting at a café
       describes the wrong event to the two people standing at it. */
    renderWithProviders(panel([landed, settled]))
    expect(
      screen.queryByText(/^handed to delivery$|^передано в доставку$/i),
    ).not.toBeInTheDocument()
  })

  it('keeps «Передано в доставку» when the parcel goes on by courier', () => {
    renderWithProviders(
      panel(
        [
          landed,
          msg({
            id: 'drop-courier',
            card_kind: 'dropoff.proposed',
            card_state: 'accepted',
            card_payload: { method: 'courier' },
          }),
        ],
        agreed({ delivery_method: 'courier' }),
      ),
    )
    expect(
      screen.getByText(/^handed to delivery$|^передано в доставку$/i),
    ).toBeInTheDocument()
    expect(screen.queryByText(/^Handed over$|^Вручено$/)).not.toBeInTheDocument()
  })
})

// ── T_UX.29 pt.3 · the checklist at the door, and our own calendar ────────

describe('the memo before the handover', () => {
  const agreed = (over: Record<string, unknown> = {}): Terms =>
    ({
      id: 't1',
      deal_id: 'd1',
      card_kind: 'terms.agreed',
      card_state: 'accepted',
      requires_ack_by: null,
      supersedes_id: null,
      payload: {
        delivery_method: 'in_person',
        price_total: 37.5,
        currency: 'USD',
        ...over,
      },
      description: null,
      created_at: '2026-09-20T10:00:00Z',
    }) as Terms

  const landed = msg({
    id: 't-arrived',
    card_kind: 'transit.update',
    card_state: 'accepted',
    card_payload: { stage: 'arrived' },
  })

  const panel = (myRole: DealRole, terms: Terms | null = agreed()) => (
    <DealStages
      dealId="d1"
      status="in_transit"
      myRole={myRole}
      terms={terms}
      deal={null}
      messages={[landed]}
      onDone={() => {}}
    />
  )

  it('tells the receiving side what to check and what to attach', () => {
    /* T_UX.29 pt.3 (owner, 2026-09-20): «У получателя нет окна подтверждения
       правильности груза и деталей для проверки… Сумма к оплате такая-то,
       проверьте… приложите скрин транзакции, квитанцию или банковский чек.»
       The sender is the payer here and there is no separate recipient, so the
       sender is the one at the door. */
    renderWithProviders(panel('sender'))
    expect(
      screen.getByText(/check the packaging|проверьте упаковку/i),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/compare the contents|Сверьте содержимое/i),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/bank slip|банковский чек/i),
    ).toBeInTheDocument()
    // The sum, stated so there is something to compare with.
    expect(screen.getByText(/37\.5 USD/)).toBeInTheDocument()
    expect(screen.getByText(/^To pay$|^К оплате$/)).toBeInTheDocument()
  })

  it('tells the side handing it over to let them look, and to screenshot the credit', () => {
    renderWithProviders(panel('carrier'))
    expect(
      screen.getByText(/do not rush them|не торопите/i),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/wait for the transfer|дождитесь перевода/i),
    ).toBeInTheDocument()
    expect(screen.getByText(/^To receive$|^К получению$/)).toBeInTheDocument()
  })

  it('does not tell a recipient to pay when the sender settles', () => {
    /* A recipient in a deal the sender pays from afar checks the parcel and
       nothing else — «передайте деньги» there is somebody else's job. */
    renderWithProviders(panel('recipient', agreed({ payer: 'sender' })))
    expect(
      screen.getByText(/check the packaging|проверьте упаковку/i),
    ).toBeInTheDocument()
    expect(screen.queryByText(/^To pay$|^К оплате$/)).not.toBeInTheDocument()
    expect(screen.queryByText(/37\.5 USD/)).not.toBeInTheDocument()
  })

  it('names the button after the act, not after sending a message', () => {
    // Owner, 2026-09-20: «И кнопка — "Завершить передачу"».
    renderWithProviders(panel('sender'))
    expect(
      screen.getByRole('button', {
        name: /complete the handover|Завершить передачу/i,
      }),
    ).toBeInTheDocument()
  })
})

describe('the calendar inside a card form', () => {
  it('is ours, not the browser’s', () => {
    /* T_UX.29 pt.3 (owner, 2026-09-20): «везде должны быть нормальные
       календари, которые разработали мы сами, а не стандартные». The native
       control takes its clock from the device, so the account's date setting
       looked broken on the busiest form in the product. */
    const { container } = renderWithProviders(
      <DealStages
        dealId="d1"
        status="in_transit"
        myRole="carrier"
        terms={null}
        deal={null}
        messages={[]}
        onDone={() => {}}
      />,
    )
    expect(container.querySelector('input[type="datetime-local"]')).toBeNull()
    expect(
      container.querySelector('button[aria-haspopup="dialog"]'),
    ).not.toBeNull()
  })
})
