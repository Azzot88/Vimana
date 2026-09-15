import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import ProfileRulesPage from '../pages/ProfileRulesPage'
import { useAuthStore } from '../stores/auth'
import type { User } from '../api/auth'
import { renderWithProviders } from './render'
import i18n from '../i18n'

/**
 * T3.12.07 pt.2 — the sender's delivery timer in «Мои правила».
 *
 * Pinned: the empty choice is the platform's default and sends `null`, a number
 * sends that number, and a refused save puts the old choice back.
 */
vi.mock('../components/AddressesSection', () => ({ default: () => null }))
vi.mock('../components/PaymentMethodsField', () => ({ default: () => null }))
vi.mock('../components/MeetingPlacesSection', () => ({ default: () => null }))
vi.mock('../components/StandingNoteSection', () => ({ default: () => null }))
vi.mock('../api/auth', async () => {
  const actual = await vi.importActual<typeof import('../api/auth')>('../api/auth')
  return { ...actual, updateMe: vi.fn() }
})

import { updateMe } from '../api/auth'

const t = i18n.t.bind(i18n)

const person = {
  id: 'u-snd',
  display_name: 'Sam',
  handle: null,
  email: 's@b.test',
  phone: null,
  can_carry: false,
  can_send: true,
  active_mode: 'sender',
  roles: ['user'],
  nostr_pubkey: null,
  business_activity_level: null,
  cancel_timeout_hours: 48,
  delivery_timeout_hours: null,
} as unknown as User

describe('delivery timeout', () => {
  beforeEach(() => {
    vi.mocked(updateMe).mockReset()
    useAuthStore.getState().setAuth(person, 'token-1')
  })

  it('starts on the platform default and saves a chosen number', async () => {
    vi.mocked(updateMe).mockResolvedValue({
      data: { ...person, delivery_timeout_hours: 48 },
    } as never)
    renderWithProviders(<ProfileRulesPage />)

    const select = screen.getByDisplayValue(t('rules.deliveryTimeout.platform'))
    fireEvent.change(select, { target: { value: '48' } })
    await waitFor(() =>
      expect(updateMe).toHaveBeenCalledWith({ delivery_timeout_hours: 48 }),
    )
  })

  it('the empty choice returns to the platform with null', async () => {
    useAuthStore.getState().setAuth({ ...person, delivery_timeout_hours: 72 }, 'token-1')
    vi.mocked(updateMe).mockResolvedValue({ data: person } as never)
    renderWithProviders(<ProfileRulesPage />)

    const select = screen.getAllByRole('combobox')[1]
    expect((select as HTMLSelectElement).value).toBe('72')
    fireEvent.change(select, { target: { value: '' } })
    await waitFor(() =>
      expect(updateMe).toHaveBeenCalledWith({ delivery_timeout_hours: null }),
    )
  })

  it('a refused save puts the old choice back', async () => {
    vi.mocked(updateMe).mockRejectedValue(new Error('no'))
    renderWithProviders(<ProfileRulesPage />)

    const select = screen.getAllByRole('combobox')[1] as HTMLSelectElement
    fireEvent.change(select, { target: { value: '120' } })
    expect(await screen.findByText(t('prefs.saveFailed'))).toBeInTheDocument()
    expect(select.value).toBe('')
  })
})
