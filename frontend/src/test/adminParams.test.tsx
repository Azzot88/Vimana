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
  return { ...actual, proposeTerms: vi.fn() }
})

import { listParams, paramHistory, setParam } from '../api/platformParams'
import { proposeTerms } from '../api/terms'

const user = (role: string): User =>
  ({
    id: 'u1',
    display_name: 'Adm',
    email: 'a@b.test',
    phone: null,
    can_carry: false,
    can_send: true,
    active_mode: 'sender',
    role,
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
  it('sends the numbers as numbers', async () => {
    const onDone = vi.fn()
    renderWithProviders(
      <TermsProposeForm dealId="d1" onDone={onDone} />,
    )
    const numbers = screen.getAllByRole('spinbutton')
    fireEvent.change(numbers[0], { target: { value: '4' } })
    fireEvent.change(numbers[1], { target: { value: '120' } })
    fireEvent.change(numbers[2], { target: { value: '900' } })
    fireEvent.click(screen.getByText(/^send$|^Отправить$/i))

    await waitFor(() =>
      expect(proposeTerms).toHaveBeenCalledWith('d1', {
        weight_kg: 4,
        price_total: 120,
        declared_value: 900,
        description: null,
        supersedes_id: null,
      }),
    )
    await waitFor(() => expect(onDone).toHaveBeenCalled())
  })

  it('carries the card it supersedes when countering', async () => {
    // A counter that does not point at what it replaces leaves two live
    // proposals and no way to tell which one is the offer.
    renderWithProviders(
      <TermsProposeForm dealId="d1" supersedesId="m-old" onDone={() => {}} />,
    )
    const numbers = screen.getAllByRole('spinbutton')
    fireEvent.change(numbers[0], { target: { value: '1' } })
    fireEvent.change(numbers[1], { target: { value: '50' } })
    fireEvent.change(numbers[2], { target: { value: '100' } })
    fireEvent.click(screen.getByText(/^send$|^Отправить$/i))

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
    renderWithProviders(<TermsProposeForm dealId="d1" onDone={onDone} />)
    const numbers = screen.getAllByRole('spinbutton')
    fireEvent.change(numbers[0], { target: { value: '1' } })
    fireEvent.change(numbers[1], { target: { value: '50' } })
    fireEvent.change(numbers[2], { target: { value: '100' } })
    fireEvent.click(screen.getByText(/^send$|^Отправить$/i))

    await waitFor(() =>
      expect(
        screen.getByText(/could not send the proposal|Не удалось отправить предложение/i),
      ).toBeInTheDocument(),
    )
    expect(onDone).not.toHaveBeenCalled()
  })
})
