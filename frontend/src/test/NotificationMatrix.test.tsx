import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import NotificationMatrix from '../components/NotificationMatrix'
import { useAuthStore } from '../stores/auth'
import type { User } from '../api/auth'
import { renderWithProviders } from './render'

/**
 * T3.32 — the matrix draws itself from the server's answer.
 *
 * The property worth pinning is that this component knows no list of its own:
 * rows and columns come from `/me`. A hardcoded list here would drift from
 * `core/notification_prefs` and start offering switches for messages nobody
 * sends — which is the exact failure the backend registry exists to prevent.
 */
vi.mock('../api/auth', async () => {
  const actual = await vi.importActual<typeof import('../api/auth')>('../api/auth')
  return { ...actual, updateMe: vi.fn() }
})

import { updateMe } from '../api/auth'

const base: User = {
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
  telegram_chat_id: 'chat-1',
  whatsapp_number: null,
  notification_prefs: {
    deal: { email: true, telegram: true },
    deadline: { email: true, telegram: false },
    security: { email: true, telegram: true },
  },
  notification_locked: ['security'],
}

const sign = (user: User) => useAuthStore.getState().setAuth(user, 'token-1')

describe('NotificationMatrix', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sign(base)
  })

  it('draws a switch per class and channel from the server answer', () => {
    renderWithProviders(<NotificationMatrix />)

    expect(screen.getByTestId('matrix-deal-email')).toBeTruthy()
    expect(screen.getByTestId('matrix-deal-telegram')).toBeTruthy()
    expect(screen.getByTestId('matrix-deadline-telegram')).toBeTruthy()
  })

  it('shows a switched-off cell as off', () => {
    renderWithProviders(<NotificationMatrix />)

    expect(screen.getByTestId('matrix-deadline-telegram').getAttribute('aria-pressed')).toBe(
      'false',
    )
    expect(screen.getByTestId('matrix-deal-telegram').getAttribute('aria-pressed')).toBe('true')
  })

  it('renders the security row as fixed rather than as switches', () => {
    // The row is shown, not hidden: an owner has to be able to see that these
    // letters exist and that they arrive whatever else is off.
    renderWithProviders(<NotificationMatrix />)

    const cell = screen.getByTestId('matrix-security-email') as HTMLButtonElement
    expect(cell.disabled).toBe(true)
    expect(cell.getAttribute('aria-pressed')).toBe('true')
  })

  it('sends only the cell that was clicked', async () => {
    const answered: User = {
      ...base,
      notification_prefs: {
        deal: { email: true, telegram: false },
        deadline: { email: true, telegram: false },
        security: { email: true, telegram: true },
      },
    }
    vi.mocked(updateMe).mockResolvedValue({ data: answered } as never)

    renderWithProviders(<NotificationMatrix />)
    fireEvent.click(screen.getByTestId('matrix-deal-telegram'))

    await waitFor(() => expect(updateMe).toHaveBeenCalledWith({
      notification_prefs: { deal: { telegram: false } },
    }))
  })

  it('does not write when a locked cell is clicked', () => {
    renderWithProviders(<NotificationMatrix />)
    fireEvent.click(screen.getByTestId('matrix-security-telegram'))

    expect(updateMe).not.toHaveBeenCalled()
  })

  it('draws nothing when no channel is live', () => {
    // An account whose channels are all switched off server-side gets an empty
    // matrix. Headers with no body read as a broken table, so the block goes.
    sign({ ...base, notification_prefs: {}, notification_locked: [] })
    const { container } = renderWithProviders(<NotificationMatrix />)

    expect(container.querySelector('table')).toBeNull()
  })
})
