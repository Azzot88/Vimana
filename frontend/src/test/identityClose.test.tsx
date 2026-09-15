import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import IdentityPage from '../pages/IdentityPage'
import type { PublicIdentity } from '../api/trust'
import { renderWithProviders } from './render'
import i18n from '../i18n'

/**
 * T3.12.06 pt.2 — close people see the addresses (owner, 2026-09-14), and the
 * page says it is for them, so it never reads as what everybody sees.
 */
vi.mock('../api/trust', async () => {
  const actual = await vi.importActual<typeof import('../api/trust')>('../api/trust')
  return { ...actual, getIdentity: vi.fn() }
})

import { getIdentity } from '../api/trust'

const t = i18n.t.bind(i18n)

const identity = (over: Partial<PublicIdentity> = {}): PublicIdentity =>
  ({
    npub: 'a'.repeat(64),
    visibility: 'full',
    display_name: 'Vera',
    avatar_url: null,
    member_since: '2026-01-01T00:00:00Z',
    uba: null,
    uba_level: null,
    highest_verification_level: null,
    verified_at: null,
    last_vouched_at: null,
    verifications_issued_count: 0,
    verifications_received_count: 0,
    dealt_with_count: 0,
    key_lost: false,
    identity_changed_at: null,
    previous_npub: null,
    archive: null,
    close: null,
    ...over,
  }) as PublicIdentity

const renderPage = () =>
  renderWithProviders(
    <Routes>
      <Route path="/i/:npub" element={<IdentityPage />} />
    </Routes>,
    { route: `/i/${'a'.repeat(64)}` },
  )

beforeEach(() => {
  vi.mocked(getIdentity).mockReset()
})

describe('IdentityPage for close people', () => {
  it('shows the addresses and meeting places, said to be for close people', async () => {
    vi.mocked(getIdentity).mockResolvedValue({
      data: identity({
        close: {
          addresses: [
            {
              label: 'Home',
              country_iso: 'PT',
              city: 'Lisbon',
              street: 'Rua Augusta 1',
              postal_code: null,
              note: null,
              is_default: true,
            },
          ],
          meeting_places: [
            { description: 'By the tram stop', country_iso: 'PT', city: null, is_default: true },
          ],
        },
      }),
    } as never)
    renderPage()
    const card = await screen.findByTestId('identity-close')
    expect(card).toHaveTextContent(t('identity.closeTitle'))
    expect(card).toHaveTextContent('Rua Augusta 1')
    expect(card).toHaveTextContent('By the tram stop')
  })

  it('shows nothing of the kind to anybody else', async () => {
    vi.mocked(getIdentity).mockResolvedValue({ data: identity() } as never)
    renderPage()
    expect(await screen.findByText('Vera')).toBeInTheDocument()
    expect(screen.queryByTestId('identity-close')).toBeNull()
  })
})
