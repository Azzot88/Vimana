import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import AdminParamsPage from '../pages/AdminParamsPage'
import TermsProposeForm from '../components/TermsProposeForm'
import { useAuthStore } from '../stores/auth'
import type { User } from '../api/auth'
import { renderWithProviders } from './render'

/**
 * T3.40 / T3.35 — the two screens that write numbers.
 *
 * The parameters screen is the one place in the product where a single person
 * changes what everyone else pays, so what is pinned here is not that the form
 * saves. It is that the screen never lets a built-in default read as a decision
 * somebody made, and that reaching it takes more than knowing the URL.
 */
vi.mock('../api/platformParams', async () => {
  const actual =
    await vi.importActual<typeof import('../api/platformParams')>(
      '../api/platformParams',
    )
  return { ...actual, listParams: vi.fn(), setParam: vi.fn(), paramHistory: vi.fn() }
})
vi.mock('../api/terms', async () => {
  const actual = await vi.importActual<typeof import('../api/terms')>('../api/terms')
  // T3.11.27 — `takeEditHold` is mocked alongside: the form takes the editing
  // window before it submits, and an unmocked one would reach the network.
  return { ...actual, proposeTerms: vi.fn(), takeEditHold: vi.fn() }
})

vi.mock('../api/dealvault', async () => {
  const actual =
    await vi.importActual<typeof import('../api/dealvault')>('../api/dealvault')
  // T3.11.27 — the proposal carries its photographs now, so the form reaches
  // for the uploader the moment one is chosen.
  return { ...actual, uploadAttachment: vi.fn() }
})

import { listParams, paramHistory, setParam } from '../api/platformParams'
import { proposeTerms } from '../api/terms'
import { uploadAttachment } from '../api/dealvault'

/** `roles` as an array, not `role` as a string.
 *
 *  `D-ROLES-ADD-UP` replaced the single column with an array and deleted
 *  `users.role`; `lib/permissions.hasRole` has read `user.roles` ever since.
 *  This fixture kept building the old shape, so `isSuperuser` was false, the
 *  page redirected, and four tests asserted against an empty document —
 *  reporting the screen broken while it worked. The `as unknown as User` cast
 *  is what let it through: it silences exactly the check that would have
 *  caught the rename.
 */
const user = (role: string): User =>
  ({
    id: 'u1',
    display_name: 'Adm',
    handle: null,
    email: 'a@b.test',
    phone: null,
    can_carry: false,
    can_send: true,
    active_mode: 'sender',
    roles: [role],
    nostr_pubkey: null,
    business_activity_level: null,
  }) as unknown as User

const sign = (role: string) => useAuthStore.getState().setAuth(user(role), 'token-1')

const row = (over: Partial<Record<string, unknown>> = {}) => ({
  key: 'carrier_fee_percent',
  scope: 'global',
  value: '3',
  value_type: 'percent' as const,
  group: 'fees',
  approved: true,
  note: 'Сбор с перевозчика',
  source: 'default' as const,
  effective_from: null,
  comment: '',
  ...over,
})

beforeEach(() => {
  vi.mocked(listParams).mockReset().mockResolvedValue([row()])
  vi.mocked(setParam).mockReset().mockResolvedValue({} as never)
  vi.mocked(paramHistory).mockReset().mockResolvedValue([])
  // T3.11.27 — reset here rather than trusting the default: one test rejects
  // the proposal on purpose, and a leaked rejection would fail the next file's
  // worth of tests with an error nobody wrote.
  vi.mocked(proposeTerms).mockReset().mockResolvedValue({ id: 'terms-1' } as never)
  vi.mocked(uploadAttachment).mockReset().mockResolvedValue({} as never)
})

describe('AdminParamsPage', () => {
  it('turns away anyone who is not a superuser', () => {
    sign('user')
    const { container } = renderWithProviders(<AdminParamsPage />)
    // Redirected — the screen renders nothing of its own.
    expect(container.querySelector('input')).toBeNull()
    expect(listParams).not.toHaveBeenCalled()
  })

  it('says out loud when a value is a built-in default', async () => {
    // Otherwise a placeholder reads as a rate somebody chose, and the next
    // person plans around a number nobody agreed to.
    sign('superuser')
    renderWithProviders(<AdminParamsPage />)
    await waitFor(() => expect(listParams).toHaveBeenCalled())
    expect(screen.getByText(/default|по умолчанию/i)).toBeInTheDocument()
  })

  it('marks a rate that is proposed rather than approved', async () => {
    sign('superuser')
    vi.mocked(listParams).mockResolvedValue([row({ approved: false })])
    renderWithProviders(<AdminParamsPage />)
    await waitFor(() =>
      expect(screen.getByText(/proposed|предложено/i)).toBeInTheDocument(),
    )
  })

  it('writes a new version with the reason, not a bare value', async () => {
    // Audit without a reason is a log. The field is offered on the same row as
    // the value so that skipping it is a choice rather than an oversight.
    sign('superuser')
    renderWithProviders(<AdminParamsPage />)
    await waitFor(() => expect(listParams).toHaveBeenCalled())

    fireEvent.click(screen.getByRole('button', { name: /change|Изменить/i }))
    const inputs = screen.getAllByRole('textbox')
    fireEvent.change(inputs[inputs.length - 2], { target: { value: '4' } })
    fireEvent.change(inputs[inputs.length - 1], { target: { value: 'решение владельца' } })
    fireEvent.click(screen.getByRole('button', { name: /save|Сохранить/i }))

    await waitFor(() =>
      expect(setParam).toHaveBeenCalledWith({
        key: 'carrier_fee_percent',
        value: '4',
        scope: 'global',
        comment: 'решение владельца',
      }),
    )
  })

  it('reloads under the corridor being viewed', async () => {
    // The minimum bond on one corridor is not the minimum on another — a screen
    // that silently showed global values would hide that.
    sign('superuser')
    renderWithProviders(<AdminParamsPage />)
    await waitFor(() => expect(listParams).toHaveBeenCalledWith('global'))

    fireEvent.change(screen.getByPlaceholderText('AE->US'), {
      target: { value: 'ae->us' },
    })
    fireEvent.click(screen.getByRole('button', { name: /apply|Применить/i }))

    await waitFor(() => expect(listParams).toHaveBeenCalledWith('AE->US'))
  })
})

describe('TermsProposeForm', () => {
  /* T3.11.27 (owner, 2026-09-12) — «Отправить» opens the preview; the proposal
     leaves on the second press. Three numbers and a settlement method are what
     the form requires, so every path below fills those and then confirms. */
  const fill = (over: { price?: string; method?: string } = {}) => {
    const numbers = screen.getAllByRole('spinbutton')
    fireEvent.change(numbers[0], { target: { value: '4' } })
    fireEvent.change(numbers[1], { target: { value: '900' } })
    fireEvent.change(numbers[2], { target: { value: over.price ?? '120' } })
    const selects = screen.getAllByRole('combobox')
    const settlement = selects[selects.length - 1]
    fireEvent.change(settlement, {
      target: { value: over.method ?? 'cash_on_delivery' },
    })
  }
  const review = () => fireEvent.click(screen.getByText(/^send$|^Отправить$/i))
  const confirm = () =>
    fireEvent.click(
      screen.getByText(/propose these terms|Предложить условия перевозчику/i),
    )

  it('shows the proposal before it sends it', async () => {
    /* «После выбора условий должно показываться окно предпросмотра перед
       отправкой в чат.» The form is long and mostly optional, so the first
       press used to be a press into the dark — the other side read the
       proposal before its author ever saw it whole. */
    renderWithProviders(
      <TermsProposeForm dealId="d1" myRole="sender" onDone={() => {}} />,
    )
    fill()
    review()

    expect(
      screen.getByText(/what the carrier will see|увидит перевозчик/i),
    ).toBeInTheDocument()
    expect(proposeTerms).not.toHaveBeenCalled()
  })

  it('goes back to editing without sending anything', async () => {
    renderWithProviders(
      <TermsProposeForm dealId="d1" myRole="sender" onDone={() => {}} />,
    )
    fill()
    review()
    fireEvent.click(screen.getByText(/back to editing|Вернуться к редактированию/i))

    expect(
      screen.queryByText(/what the carrier will see|увидит перевозчик/i),
    ).not.toBeInTheDocument()
    expect(proposeTerms).not.toHaveBeenCalled()
  })

  it('sends the numbers as numbers, and the settlement with them', async () => {
    const onDone = vi.fn()
    renderWithProviders(
      <TermsProposeForm dealId="d1" myRole="sender" onDone={onDone} />,
    )
    fill()
    review()
    confirm()

    await waitFor(() =>
      expect(proposeTerms).toHaveBeenCalledWith(
        'd1',
        expect.objectContaining({
          weight_kg: 4,
          price_total: 120,
          declared_value: 900,
          // T3.11.27 — «Способ оплаты» moved inside the form: it was a chip
          // beside it, raising a second card about the same agreement.
          payment_method: 'cash_on_delivery',
          description: null,
          supersedes_id: null,
          payer: 'sender',
        }),
      ),
    )
    await waitFor(() => expect(onDone).toHaveBeenCalled())
  })

  it('carries the card it supersedes when countering', async () => {
    // A counter that does not point at what it replaces leaves two live
    // proposals and no way to tell which one is the offer.
    renderWithProviders(
      <TermsProposeForm
        dealId="d1"
        supersedesId="m-old"
        myRole="sender"
        onDone={() => {}}
      />,
    )
    fill({ price: '100' })
    review()
    confirm()

    await waitFor(() =>
      expect(proposeTerms).toHaveBeenCalledWith(
        'd1',
        expect.objectContaining({ supersedes_id: 'm-old' }),
      ),
    )
  })

  it('reports a refusal instead of pretending it sent', async () => {
    vi.mocked(proposeTerms).mockRejectedValue(new Error('nope'))
    const onDone = vi.fn()
    renderWithProviders(
      <TermsProposeForm dealId="d1" myRole="sender" onDone={onDone} />,
    )
    fill({ price: '100' })
    review()
    confirm()

    await waitFor(() =>
      expect(
        screen.getByText(/could not send the proposal|Не удалось отправить предложение/i),
      ).toBeInTheDocument(),
    )
    expect(onDone).not.toHaveBeenCalled()
  })

  it('hangs the chosen photos on the proposal itself', async () => {
    /* «Над кнопкой добавить возможность загрузки нескольких фото товара.» They
       attach to the proposal, not to a chat row beside it — a picture filed
       beside an act is the defect this whole batch is about. */
    vi.mocked(proposeTerms).mockResolvedValue({ id: 'terms-1' } as never)
    renderWithProviders(
      <TermsProposeForm dealId="d1" myRole="sender" onDone={() => {}} />,
    )
    fill()
    const input = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement
    const one = new File(['a'], 'front.png', { type: 'image/png' })
    const two = new File(['b'], 'back.png', { type: 'image/png' })
    fireEvent.change(input, { target: { files: [one, two] } })
    review()
    confirm()

    await waitFor(() =>
      expect(uploadAttachment).toHaveBeenCalledWith(
        'd1',
        'terms-1',
        one,
        'cargo_photo',
      ),
    )
    expect(uploadAttachment).toHaveBeenCalledWith(
      'd1',
      'terms-1',
      two,
      'cargo_photo',
    )
  })

  it('offers only the handover methods this carrier published', () => {
    /* «Условия передачи товара в отправку выбирает Перевозчик… при формировании
       рейса» — the same master rule as the categories. Offering a sender
       «постамат» on a trip whose carrier only meets people is offering them a
       refusal. */
    renderWithProviders(
      <TermsProposeForm
        dealId="d1"
        myRole="sender"
        fromBoard={
          {
            trip_handover_methods: ['in_person'],
            trip_delivery_methods: ['in_person', 'local_post'],
          } as never
        }
        onDone={() => {}}
      />,
    )
    const [handover] = screen.getAllByRole('combobox')
    const values = Array.from(handover.querySelectorAll('option')).map(
      (o) => (o as HTMLOptionElement).value,
    )
    expect(values).toEqual(['', 'in_person'])
  })

  it('offers all of them when the trip named none', () => {
    // Silence is not a refusal: `allowed` empty means the carrier said nothing,
    // and a form with one option would invent a restriction they never stated.
    renderWithProviders(
      <TermsProposeForm dealId="d1" myRole="sender" onDone={() => {}} />,
    )
    const [handover] = screen.getAllByRole('combobox')
    expect(handover.querySelectorAll('option').length).toBe(6)
  })
})
