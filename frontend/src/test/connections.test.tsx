import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import ConnectionsSection from '../components/ConnectionsSection'
import type { ClosePair, Connection } from '../api/social'
import { renderWithProviders } from './render'
import i18n from '../i18n'

/**
 * T3.12.06 — closeness is asked and accepted (owner, 2026-09-14).
 *
 * Pinned: a contact row asks rather than declares; an unanswered request of mine
 * can be withdrawn; a request made of me is answered where it stands.
 */
vi.mock('../api/social', async () => {
  const actual = await vi.importActual<typeof import('../api/social')>('../api/social')
  return {
    ...actual,
    listConnections: vi.fn(),
    listClose: vi.fn(),
    requestClose: vi.fn(),
    acceptClose: vi.fn(),
    declineClose: vi.fn(),
    endClose: vi.fn(),
    removeConnection: vi.fn(),
  }
})

import {
  acceptClose,
  endClose,
  listClose,
  listConnections,
  requestClose,
} from '../api/social'

const t = i18n.t.bind(i18n)

const contact = (id: string, name: string, state: Connection['state']): Connection =>
  ({
    id: `c-${id}`,
    connected_user_id: id,
    connected_user: { display_name: name, active_mode: 'sender' },
    created_at: '2026-09-14T10:00:00Z',
    state,
  }) as unknown as Connection

const request: ClosePair = {
  id: 'p-1',
  user_id: 'u-mira',
  display_name: 'Mira',
  handle: null,
  state: 'close_requested',
  requested_at: '2026-09-14T10:00:00Z',
  accepted_at: null,
}

beforeEach(() => {
  vi.mocked(listConnections).mockReset().mockResolvedValue({
    data: [contact('u-anna', 'Anna', 'connection'), contact('u-boris', 'Boris', 'close_pending')],
  } as never)
  vi.mocked(listClose).mockReset().mockResolvedValue({ data: [request] } as never)
  vi.mocked(requestClose).mockReset().mockResolvedValue({} as never)
  vi.mocked(acceptClose).mockReset().mockResolvedValue({} as never)
  vi.mocked(endClose).mockReset().mockResolvedValue({} as never)
})

describe('ConnectionsSection', () => {
  it('asks a contact to be close rather than declaring it', async () => {
    renderWithProviders(<ConnectionsSection />)
    fireEvent.click(await screen.findByText(t('contacts.makeClose')))
    await waitFor(() => expect(requestClose).toHaveBeenCalledWith('u-anna'))
  })

  it('withdraws a request nobody has answered', async () => {
    renderWithProviders(<ConnectionsSection />)
    expect(await screen.findByText(t('contacts.closePending'))).toBeInTheDocument()
    fireEvent.click(screen.getByText(t('contacts.cancelRequest')))
    await waitFor(() => expect(endClose).toHaveBeenCalledWith('u-boris'))
  })

  it('answers a request made of me where it stands', async () => {
    renderWithProviders(<ConnectionsSection />)
    expect(await screen.findByTestId('close-request')).toHaveTextContent('Mira')
    fireEvent.click(screen.getByText(t('contacts.closeAccept')))
    await waitFor(() => expect(acceptClose).toHaveBeenCalledWith('p-1'))
  })
})
