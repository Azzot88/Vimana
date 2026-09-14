import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import JoinDealPage from '../pages/JoinDealPage'
import RecipientOfferSection from '../components/RecipientOfferSection'
import { useAuthStore } from '../stores/auth'
import type { User } from '../api/auth'
import type { RecipientOffer } from '../api/participants'
import { renderWithProviders } from './render'
import i18n from '../i18n'

/**
 * T3.12.05 — the recipient is offered the role and answers.
 *
 * Owner, 2026-09-14: opening a link no longer makes somebody the recipient. What
 * is pinned is that the link shows an offer rather than a deal, that each of the
 * three answers sends what it says, and that the account setting is one press.
 */
vi.mock('../api/participants', async () => {
  const actual =
    await vi.importActual<typeof import('../api/participants')>('../api/participants')
  return {
    ...actual,
    claimInvite: vi.fn(),
    myRecipientOffers: vi.fn(),
    acceptRecipientOffer: vi.fn(),
    declineRecipientOffer: vi.fn(),
  }
})
vi.mock('../api/auth', async () => {
  const actual = await vi.importActual<typeof import('../api/auth')>('../api/auth')
  return { ...actual, updateMe: vi.fn() }
})

import {
  acceptRecipientOffer,
  claimInvite,
  declineRecipientOffer,
  myRecipientOffers,
} from '../api/participants'
import { updateMe } from '../api/auth'

const t = i18n.t.bind(i18n)

const person = {
  id: 'u-rec',
  display_name: 'Vera',
  handle: null,
  email: 'v@b.test',
  phone: null,
  can_carry: false,
  can_send: true,
  active_mode: 'sender',
  roles: ['user'],
  nostr_pubkey: null,
  business_activity_level: null,
  refuses_recipient_offers: false,
} as unknown as User

const offer: RecipientOffer = {
  id: 'o1',
  deal_id: 'd1',
  state: 'pending',
  route: 'DXB → JFK',
  depart_at: '2030-01-10T10:00:00Z',
  sender_name: 'Anna',
  cargo_description: 'Spare keys',
  invited_at: '2026-09-14T10:00:00Z',
}

const renderJoin = () =>
  renderWithProviders(
    <Routes>
      <Route path="/join/deal/:token" element={<JoinDealPage />} />
    </Routes>,
    { route: '/join/deal/tok' },
  )

beforeEach(() => {
  useAuthStore.getState().setAuth(person, 'token-1')
  vi.mocked(claimInvite).mockReset().mockResolvedValue({ data: offer } as never)
  vi.mocked(myRecipientOffers).mockReset().mockResolvedValue({ data: [offer] } as never)
  vi.mocked(acceptRecipientOffer)
    .mockReset()
    .mockResolvedValue({ data: { ...offer, state: 'accepted' } } as never)
  vi.mocked(declineRecipientOffer)
    .mockReset()
    .mockResolvedValue({ data: { ...offer, state: 'declined' } } as never)
  vi.mocked(updateMe)
    .mockReset()
    .mockResolvedValue({ data: { ...person, refuses_recipient_offers: true } } as never)
})

describe('JoinDealPage', () => {
  it('shows the offer, not the deal', async () => {
    renderJoin()
    expect(await screen.findByText('DXB → JFK')).toBeInTheDocument()
    expect(screen.getByText('Anna')).toBeInTheDocument()
    expect(screen.getByText(t('recipientOffer.nothingYet'))).toBeInTheDocument()
    expect(claimInvite).toHaveBeenCalledWith('tok')
    expect(acceptRecipientOffer).not.toHaveBeenCalled()
  })

  it('accepts only when asked to', async () => {
    renderJoin()
    fireEvent.click(await screen.findByRole('button', { name: t('recipientOffer.accept') }))
    await waitFor(() => expect(acceptRecipientOffer).toHaveBeenCalledWith('o1'))
  })

  it('can decline and refuse the next offers in one press', async () => {
    renderJoin()
    fireEvent.click(
      await screen.findByRole('button', { name: t('recipientOffer.declineRefuse') }),
    )
    await waitFor(() => expect(declineRecipientOffer).toHaveBeenCalledWith('o1', true))
    expect(await screen.findByText(t('recipientOffer.declined'))).toBeInTheDocument()
  })

  it('says why when the link cannot be used', async () => {
    vi.mocked(claimInvite).mockRejectedValue({
      response: { data: { detail: 'This invite was withdrawn' } },
    })
    renderJoin()
    expect(await screen.findByText('This invite was withdrawn')).toBeInTheDocument()
  })
})

describe('RecipientOfferSection', () => {
  it('lists the open offers and a plain decline keeps the setting as it was', async () => {
    renderWithProviders(<RecipientOfferSection />)
    expect(await screen.findByTestId('recipient-offer')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: t('recipientOffer.decline') }))
    await waitFor(() => expect(declineRecipientOffer).toHaveBeenCalledWith('o1', false))
    await waitFor(() => expect(screen.queryByTestId('recipient-offer')).toBeNull())
    expect(updateMe).not.toHaveBeenCalled()
  })

  it('turns the refusal on without an offer to refuse', async () => {
    vi.mocked(myRecipientOffers).mockResolvedValue({ data: [] } as never)
    renderWithProviders(<RecipientOfferSection />)
    fireEvent.click(screen.getByLabelText(new RegExp(t('recipientOffer.refuseToggle'))))
    await waitFor(() =>
      expect(updateMe).toHaveBeenCalledWith({ refuses_recipient_offers: true }),
    )
  })
})
