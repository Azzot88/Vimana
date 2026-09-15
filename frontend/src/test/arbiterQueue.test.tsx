import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import ArbiterQueue from '../components/ArbiterQueue'
import { useAuthStore } from '../stores/auth'
import type { User } from '../api/auth'
import type { Dispute } from '../api/admin'
import { renderWithProviders } from './render'
import i18n from '../i18n'

/**
 * T3.12.09 — the arbiter answers the pool's offer.
 *
 * Pinned: an offer made to this arbiter shows «принять / отказаться» and each
 * sends its answer; the claim button appears only where the server says the
 * dispute may be taken (`requests` mode).
 */
vi.mock('../api/admin', async () => {
  const actual = await vi.importActual<typeof import('../api/admin')>('../api/admin')
  return {
    ...actual,
    listDisputes: vi.fn(),
    acceptDispute: vi.fn(),
    declineDispute: vi.fn(),
    claimDispute: vi.fn(),
  }
})

import { acceptDispute, declineDispute, listDisputes } from '../api/admin'

const t = i18n.t.bind(i18n)

const arbiter = {
  id: 'arb-1',
  display_name: 'Ada',
  handle: null,
  email: 'a@b.test',
  phone: null,
  can_carry: false,
  can_send: true,
  active_mode: 'sender',
  roles: ['arbiter'],
  nostr_pubkey: null,
  business_activity_level: null,
} as unknown as User

const dispute = (over: Partial<Dispute>): Dispute => ({
  id: 'd-1',
  deal_id: 'deal-1',
  opened_by: 'u-1',
  arbiter_id: null,
  reason: 'other',
  status: 'open',
  verdict: null,
  created_at: '2026-09-15T00:00:00Z',
  resolved_at: null,
  offered_to_id: null,
  offered_at: null,
  claimable: false,
  ...over,
})

const serve = (items: Dispute[]) =>
  vi.mocked(listDisputes).mockResolvedValue({
    data: { items, next_cursor: null },
  } as never)

describe('ArbiterQueue · the pool', () => {
  beforeEach(() => {
    vi.mocked(listDisputes).mockReset()
    vi.mocked(acceptDispute).mockReset().mockResolvedValue({ data: {} } as never)
    vi.mocked(declineDispute).mockReset().mockResolvedValue({ data: {} } as never)
    useAuthStore.getState().setAuth(arbiter, 'token-1')
  })

  it('an offer to me is accepted with one press', async () => {
    serve([dispute({ offered_to_id: 'arb-1' })])
    renderWithProviders(<ArbiterQueue />)
    fireEvent.click(await screen.findByText(t('admin.accept')))
    await waitFor(() => expect(acceptDispute).toHaveBeenCalledWith('d-1'))
  })

  it('and declined with the other', async () => {
    serve([dispute({ offered_to_id: 'arb-1' })])
    renderWithProviders(<ArbiterQueue />)
    fireEvent.click(await screen.findByText(t('admin.decline')))
    await waitFor(() => expect(declineDispute).toHaveBeenCalledWith('d-1'))
  })

  it('nothing to take from the queue unless the server allows it', async () => {
    serve([dispute({ id: 'd-2', offered_to_id: 'someone-else' })])
    renderWithProviders(<ArbiterQueue />)
    await screen.findByText('#d-2')
    expect(screen.queryByText(t('admin.claim'))).not.toBeInTheDocument()
    expect(screen.queryByText(t('admin.accept'))).not.toBeInTheDocument()
  })

  it('offers the claim in requests mode', async () => {
    serve([dispute({ id: 'd-3', claimable: true })])
    renderWithProviders(<ArbiterQueue />)
    expect(await screen.findByText(t('admin.claim'))).toBeInTheDocument()
  })
})
