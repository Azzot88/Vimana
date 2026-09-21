import { describe, expect, it, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from './render'

/**
 * T_UX.29 pt.7 — the bell.
 *
 * What is worth pinning here is the rule, not the markup: the panel answers
 * «что я пропустил», so the count is what nobody has seen, and opening the
 * panel is not the same as having dealt with it (owner, 2026-09-20).
 */
vi.mock('../api/notifications', async () => {
  const actual = await vi.importActual<typeof import('../api/notifications')>(
    '../api/notifications',
  )
  return {
    ...actual,
    listNotifications: vi.fn(),
    unreadCount: vi.fn(),
    markRead: vi.fn(),
  }
})
// The live stream opens a `fetch` that never ends; in jsdom it would hang the
// test and teach nobody anything. The beat and the stream do the same thing
// here — ask the count again — and the beat is the one that is testable.
vi.mock('../hooks/useEventStream', () => ({ useEventStream: () => {} }))

import {
  listNotifications,
  markRead,
  unreadCount,
} from '../api/notifications'
import NotificationBell from '../components/NotificationBell'

const row = (over: Record<string, unknown> = {}) => ({
  id: 'n1',
  kind: 'deal.status',
  deal_id: 'd1',
  trip_id: null,
  payload: null,
  created_at: '2026-09-20T10:00:00Z',
  read_at: null,
  ...over,
})

beforeEach(() => {
  vi.mocked(unreadCount).mockReset().mockResolvedValue({ data: { unread: 0 } } as never)
  vi.mocked(listNotifications).mockReset().mockResolvedValue({ data: [] } as never)
  vi.mocked(markRead).mockReset().mockResolvedValue({ data: { unread: 0 } } as never)
})

describe('NotificationBell', () => {
  it('says nothing when nothing was missed', async () => {
    renderWithProviders(<NotificationBell />)
    await waitFor(() => expect(unreadCount).toHaveBeenCalled())
    // No badge: «есть что-то» is a claim, and there is nothing.
    expect(screen.queryByText('1')).not.toBeInTheDocument()
  })

  it('shows how many, not merely that there are some', async () => {
    /* A dot would say «что-то есть»; the number is what makes somebody open it
       now rather than later. */
    vi.mocked(unreadCount).mockResolvedValue({ data: { unread: 3 } } as never)
    renderWithProviders(<NotificationBell />)
    expect(await screen.findByText('3')).toBeInTheDocument()
  })

  it('opening the panel does not mark anything read', async () => {
    /* Somebody who glances at the list and closes it has not dealt with
       anything, and a list that empties itself on sight cannot be re-read by
       the person who was too quick. */
    vi.mocked(unreadCount).mockResolvedValue({ data: { unread: 1 } } as never)
    vi.mocked(listNotifications).mockResolvedValue({ data: [row()] } as never)
    renderWithProviders(<NotificationBell />)

    await userEvent.click(await screen.findByRole('button', { name: /bell|Оповещения|Сповіщення|Powiadomienia|Notifications|Notificaciones/i }))
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    expect(markRead).not.toHaveBeenCalled()
  })

  it('marks everything read only when asked', async () => {
    vi.mocked(unreadCount).mockResolvedValue({ data: { unread: 2 } } as never)
    vi.mocked(listNotifications).mockResolvedValue({ data: [row()] } as never)
    renderWithProviders(<NotificationBell />)

    await userEvent.click(await screen.findByRole('button', { name: /bell|Оповещения|Сповіщення|Powiadomienia|Notifications|Notificaciones/i }))
    await userEvent.click(
      await screen.findByRole('button', {
        name: /mark all|Прочитать все|Прочитати всі|Oznacz|Tout marquer|Marcar todo/i,
      }),
    )
    expect(markRead).toHaveBeenCalledWith({})
  })
})
