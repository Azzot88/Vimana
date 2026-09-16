import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import ProfileVaultPage from '../pages/ProfileVaultPage'
import type { Deal } from '../api/deals'
import type { SafeFile } from '../api/dealvault'
import { renderWithProviders } from './render'
import i18n from '../i18n'

/**
 * T_UX.27 — the vault as a place.
 *
 * Owner, 2026-09-15. Pinned: closed deals are listed rather than hidden, every
 * deal leads into its vault, and a file says which deals it went to.
 */
vi.mock('../api/deals', async () => {
  const actual = await vi.importActual<typeof import('../api/deals')>('../api/deals')
  return { ...actual, listDeals: vi.fn() }
})
vi.mock('../api/dealvault', async () => {
  const actual = await vi.importActual<typeof import('../api/dealvault')>('../api/dealvault')
  return { ...actual, listMyFiles: vi.fn() }
})

import { listDeals } from '../api/deals'
import { listMyFiles } from '../api/dealvault'

const t = i18n.t.bind(i18n)

const deal = (over: Partial<Deal>): Deal =>
  ({
    id: 'deal-live',
    cargo_id: 'c1',
    trip_id: 't1',
    sender_id: 's1',
    carrier_id: 'c2',
    recipient_id: null,
    status: 'in_transit',
    created_at: '2026-09-15T00:00:00Z',
    origin: 'DXB',
    destination: 'JFK',
    deal_no: 'PF-482-19375-1',
    cargo_description: 'papers',
    ...over,
  }) as Deal

const file: SafeFile = {
  id: 'f1',
  file_hash: 'abc',
  kind: 'doc' as SafeFile['kind'],
  mime: 'image/png',
  size_bytes: 2048,
  scan_status: 'clean',
  url: 'https://files.test/f1.png',
  first_provided_at: '2026-09-01T10:00:00Z',
  attached_to: [{ deal_id: 'deal-old', deal_no: 'PF-482-19375-2' }],
}

describe('ProfileVaultPage', () => {
  beforeEach(() => {
    vi.mocked(listDeals).mockReset()
    vi.mocked(listMyFiles).mockReset()
  })

  const serve = (deals: Deal[], files: SafeFile[]) => {
    vi.mocked(listDeals).mockResolvedValue({
      data: { items: deals, next_cursor: null },
    } as never)
    vi.mocked(listMyFiles).mockResolvedValue({ data: files } as never)
  }

  it('lists closed deals beside the live ones, each leading into its vault', async () => {
    serve(
      [deal({}), deal({ id: 'deal-done', status: 'closed', deal_no: 'PF-482-19375-9' })],
      [],
    )
    renderWithProviders(<ProfileVaultPage />)

    expect(await screen.findByText(t('vault.active'))).toBeInTheDocument()
    expect(screen.getByText(t('vault.closed'))).toBeInTheDocument()
    const links = screen.getAllByRole('link')
    const targets = links.map((a) => a.getAttribute('href'))
    expect(targets).toContain('/deals/deal-live/vault')
    expect(targets).toContain('/deals/deal-done/vault')
  })

  it('a file says which deal it went to', async () => {
    serve([], [file])
    renderWithProviders(<ProfileVaultPage />)

    expect(await screen.findByText('PF-482-19375-2')).toBeInTheDocument()
    expect(screen.getByText(t('vault.openFile'))).toBeInTheDocument()
  })

  it('says the safe is empty rather than drawing nothing', async () => {
    serve([], [])
    renderWithProviders(<ProfileVaultPage />)

    expect(await screen.findByText(t('vault.noFiles'))).toBeInTheDocument()
    expect(screen.getByText(t('vault.noDeals'))).toBeInTheDocument()
  })
})
