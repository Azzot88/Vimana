import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import NotificationMatrix from '../components/NotificationMatrix'
import { useAuthStore } from '../stores/auth'
import type { User } from '../api/auth'
import { renderWithProviders } from './render'

/**
 * T3.32 — the matrix draws itself from the server's answer.
 *
 * Two properties are pinned here. First, this component knows no list of its
 * own: rows and columns come from `/me`, and a hardcoded list would drift from
 * `core/notification_prefs`. Second, a column the account cannot be reached on
 * is visibly unusable rather than absent — the earlier version hid it, which
 * left a person unable to tell whether the channel exists here at all.
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
  roles: [],
  nostr_pubkey: null,
  business_activity_level: null,
  notify_email: true,
  notify_telegram: false,
  notify_whatsapp: false,
  telegram_chat_id: 'chat-1',
  whatsapp_number: null,
  notification_prefs: {
    deal: { email: true, telegram: true, whatsapp: true },
    deadline: { email: true, telegram: false, whatsapp: true },
    security: { email: true, telegram: true, whatsapp: true },
  },
  notification_locked: ['security'],
  // Mail and Telegram are reachable; WhatsApp has no number on this account.
  notification_channels: { email: true, telegram: true, whatsapp: false },
}

const sign = (user: User) => useAuthStore.getState().setAuth(user, 'token-1')

const cell = (id: string) => screen.getByTestId(id) as HTMLInputElement

describe('NotificationMatrix', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sign(base)
  })

  it('draws a checkbox per class and channel from the server answer', () => {
    renderWithProviders(<NotificationMatrix />)

    expect(cell('matrix-deal-email').type).toBe('checkbox')
    expect(cell('matrix-deal-telegram')).toBeTruthy()
    expect(cell('matrix-deadline-whatsapp')).toBeTruthy()
  })

  it('shows a switched-off cell as unchecked', () => {
    renderWithProviders(<NotificationMatrix />)

    expect(cell('matrix-deadline-telegram').checked).toBe(false)
    expect(cell('matrix-deal-telegram').checked).toBe(true)
  })

  it('keeps an unreachable channel visible but unusable', () => {
    // Stored `true`, no number: nothing will arrive, so the box must not claim
    // otherwise. The column stays — hiding it hid the fact WhatsApp exists.
    renderWithProviders(<NotificationMatrix />)

    const box = cell('matrix-deal-whatsapp')
    expect(box.disabled).toBe(true)
    expect(box.checked).toBe(false)
    expect(screen.getAllByText(/not connected|не подключён/i).length).toBeGreaterThan(0)
  })

  it('renders the security row as fixed rather than as choices', () => {
    // The row is shown, not hidden: an owner has to be able to see that these
    // letters exist and that they arrive whatever else is off.
    renderWithProviders(<NotificationMatrix />)

    const box = cell('matrix-security-email')
    expect(box.disabled).toBe(true)
    expect(box.checked).toBe(true)
  })

  it('sends only the cell that was clicked', async () => {
    vi.mocked(updateMe).mockResolvedValue({ data: base } as never)

    renderWithProviders(<NotificationMatrix />)
    fireEvent.click(cell('matrix-deal-telegram'))

    await waitFor(() => expect(updateMe).toHaveBeenCalledWith({
      notification_prefs: { deal: { telegram: false } },
    }))
  })

  it('does not write when a locked cell is clicked', () => {
    renderWithProviders(<NotificationMatrix />)
    fireEvent.click(cell('matrix-security-telegram'))

    expect(updateMe).not.toHaveBeenCalled()
  })

  it('does not write when an unreachable cell is clicked', () => {
    renderWithProviders(<NotificationMatrix />)
    fireEvent.click(cell('matrix-deal-whatsapp'))

    expect(updateMe).not.toHaveBeenCalled()
  })

  it('draws nothing before /me has answered', () => {
    sign({ ...base, notification_prefs: {}, notification_locked: [] })
    const { container } = renderWithProviders(<NotificationMatrix />)

    expect(container.querySelector('table')).toBeNull()
  })
})
