import { afterEach, describe, expect, it, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { act, screen, waitFor, within } from '@testing-library/react'
import LanguageSwitcher from '../components/LanguageSwitcher'
import { renderWithProviders } from './render'
import i18n from '../i18n'
import { useAuthStore } from '../stores/auth'
import type { User } from '../api/auth'

vi.mock('../api/auth', async () => {
  const actual = await vi.importActual<typeof import('../api/auth')>('../api/auth')
  return { ...actual, updateMe: vi.fn() }
})

import { updateMe } from '../api/auth'

describe('LanguageSwitcher', () => {
  it('opens dropdown with 6 endonym-named languages', async () => {
    const user = userEvent.setup()
    renderWithProviders(<LanguageSwitcher />)

    await user.click(screen.getByRole('button'))
    const list = screen.getByRole('list')
    expect(within(list).getByText('English')).toBeInTheDocument()
    expect(within(list).getByText('Українська')).toBeInTheDocument()
    expect(within(list).getByText('Русский')).toBeInTheDocument()
    expect(within(list).getByText('Polski')).toBeInTheDocument()
    expect(within(list).getByText('Français')).toBeInTheDocument()
    expect(within(list).getByText('Español')).toBeInTheDocument()
  })

  it('changes i18n language and persists to localStorage on click', async () => {
    const user = userEvent.setup()
    renderWithProviders(<LanguageSwitcher />)

    await user.click(screen.getByRole('button'))
    const list = screen.getByRole('list')
    await user.click(within(list).getByText('Русский'))

    // `changeLanguage` resolves after the click handler returns, and the
    // re-render it causes lands outside `act` — which is what the warning in
    // the output was about. Waiting for the settled value puts that update
    // inside `act` and, incidentally, tests the thing that actually matters:
    // the switch completes, not that it started.
    await waitFor(() => expect(i18n.language).toBe('ru'))
    expect(localStorage.getItem('lang')).toBe('ru')

    // The reset is a state update too, so it needs the same treatment or the
    // warning simply moves to the end of the test.
    await act(async () => {
      await i18n.changeLanguage('en')
    })
  })
})

// ── T3.33 · letters follow the interface ─────────────────────────────────────

const member: User = {
  id: 'u1',
  display_name: 'Nick',
  email: 'nick@example.test',
  phone: null,
  can_carry: true,
  can_send: true,
  active_mode: 'sender',
  role: 'user',
  nostr_pubkey: null,
  business_activity_level: null,
  notify_email: true,
  notify_telegram: false,
  notify_whatsapp: false,
  telegram_chat_id: null,
  whatsapp_number: null,
  locale: 'en',
}

describe('LanguageSwitcher · the account follows', () => {
  afterEach(async () => {
    useAuthStore.setState({ user: null, token: null })
    vi.clearAllMocks()
    await act(async () => {
      await i18n.changeLanguage('en')
    })
  })

  it('writes the new language to the account of a signed-in reader', async () => {
    vi.mocked(updateMe).mockResolvedValue({ data: { ...member, locale: 'pl' } } as never)
    useAuthStore.getState().setAuth(member, 'token-1')

    const user = userEvent.setup()
    renderWithProviders(<LanguageSwitcher />)
    await user.click(screen.getByRole('button'))
    await user.click(within(screen.getByRole('list')).getByText('Polski'))

    await waitFor(() => expect(updateMe).toHaveBeenCalledWith({ locale: 'pl' }))
  })

  it('writes nothing for a stranger', async () => {
    // The landing page has this switcher too, and there is no account to write
    // to. A request here would be a 401 on every language change.
    const user = userEvent.setup()
    renderWithProviders(<LanguageSwitcher />)
    await user.click(screen.getByRole('button'))
    await user.click(within(screen.getByRole('list')).getByText('Polski'))

    await waitFor(() => expect(i18n.language).toBe('pl'))
    expect(updateMe).not.toHaveBeenCalled()
  })

  it('writes nothing when the account already reads that language', async () => {
    useAuthStore.getState().setAuth({ ...member, locale: 'pl' }, 'token-1')

    const user = userEvent.setup()
    renderWithProviders(<LanguageSwitcher />)
    await user.click(screen.getByRole('button'))
    await user.click(within(screen.getByRole('list')).getByText('Polski'))

    await waitFor(() => expect(i18n.language).toBe('pl'))
    expect(updateMe).not.toHaveBeenCalled()
  })
})
