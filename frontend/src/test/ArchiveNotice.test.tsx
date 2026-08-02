import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import ArchiveNotice from '../components/ArchiveNotice'
import type { User } from '../api/auth'
import * as keypair from '../api/keypair'
import type { KeypairStatus } from '../api/keypair'
import i18n from '../i18n'
import { renderWithProviders } from './render'

/**
 * T3.19 — what a retired identity is told, and the one choice it still has.
 *
 * The properties worth pinning are the ones that are easy to break by making
 * the UI tidier: that closing the dialog is not an answer, that the deadline is
 * named rather than implied, and that the irreversible direction needs a
 * deliberate act. Each of those is a promise the product makes in words.
 */
vi.mock('../api/keypair', async () => {
  const actual = await vi.importActual<typeof import('../api/keypair')>('../api/keypair')
  return {
    ...actual,
    getKeypairStatus: vi.fn(),
    markArchiveNoticeSeen: vi.fn(),
    setArchiveChoice: vi.fn(),
  }
})

let currentUser: User | null = null
vi.mock('../stores/auth', () => ({
  useAuthStore: (selector: (s: { user: User | null }) => unknown) =>
    selector({ user: currentUser }),
}))

const retiredUser: User = {
  id: 'u1',
  display_name: 'Nick',
  email: 'a@b.test',
  phone: null,
  can_carry: true,
  can_send: true,
  active_mode: 'carrier',
  role: 'user',
  nostr_pubkey: 'ab'.repeat(32),
  business_activity_level: null,
  notify_email: true,
  notify_telegram: false,
  notify_whatsapp: false,
  telegram_chat_id: null,
  whatsapp_number: null,
  key_lost: true,
}

const status = (over: Partial<KeypairStatus> = {}): KeypairStatus => ({
  npub: 'ab'.repeat(32),
  identity_established: true,
  key_lost: true,
  key_copies: 'user_only',
  previous_npub: null,
  identity_changed_at: null,
  archive_choice: null,
  archive_notice_seen_at: null,
  archive_window_ends_at: new Date(Date.now() + 10 * 86_400_000).toISOString(),
  ...over,
})

describe('ArchiveNotice', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    currentUser = retiredUser
    vi.mocked(keypair.getKeypairStatus).mockResolvedValue({ data: status() } as never)
    vi.mocked(keypair.markArchiveNoticeSeen).mockResolvedValue({
      data: status({ archive_notice_seen_at: new Date().toISOString() }),
    } as never)
    vi.mocked(keypair.setArchiveChoice).mockResolvedValue({
      data: status({ archive_choice: 'hide', archive_notice_seen_at: new Date().toISOString() }),
    } as never)
  })

  it('asks the server nothing while the key is alive', () => {
    currentUser = { ...retiredUser, key_lost: false }
    renderWithProviders(<ArchiveNotice />)
    expect(keypair.getKeypairStatus).not.toHaveBeenCalled()
    expect(screen.queryByTestId('archive-banner')).toBeNull()
  })

  it('explains itself once, on the first sign-in after the loss', async () => {
    renderWithProviders(<ArchiveNotice />)
    expect(await screen.findByTestId('archive-modal')).toBeTruthy()
  })

  it('stays quiet in the modal once the notice has been seen', async () => {
    vi.mocked(keypair.getKeypairStatus).mockResolvedValue({
      data: status({ archive_notice_seen_at: new Date().toISOString() }),
    } as never)
    renderWithProviders(<ArchiveNotice />)
    expect(await screen.findByTestId('archive-banner')).toBeTruthy()
    expect(screen.queryByTestId('archive-modal')).toBeNull()
  })

  it('does not read a closed dialog as a decision', async () => {
    renderWithProviders(<ArchiveNotice />)
    fireEvent.click(await screen.findByTestId('archive-decide-later'))
    await waitFor(() => expect(keypair.markArchiveNoticeSeen).toHaveBeenCalled())
    // The default the dialog described is reached by silence, not by consent
    // harvested from a close button.
    expect(keypair.setArchiveChoice).not.toHaveBeenCalled()
  })

  it('names the date after which silence becomes the answer', async () => {
    renderWithProviders(<ArchiveNotice />)
    const banner = await screen.findByTestId('archive-banner')
    expect(banner.getAttribute('data-state')).toBe('undecided')
    const deadline = new Date(Date.now() + 10 * 86_400_000).toLocaleDateString(
      i18n.language,
    )
    expect(banner.textContent).toContain(deadline)
  })

  it('will not close the archive on a single click', async () => {
    renderWithProviders(<ArchiveNotice />)
    fireEvent.click(await screen.findByTestId('archive-choose-hide'))

    const confirm = screen.getByTestId('archive-hide-confirm') as HTMLButtonElement
    expect(confirm.disabled).toBe(true)
    fireEvent.click(confirm)
    expect(keypair.setArchiveChoice).not.toHaveBeenCalled()

    fireEvent.click(screen.getByTestId('archive-hide-understood'))
    fireEvent.click(confirm)
    await waitFor(() =>
      expect(keypair.setArchiveChoice).toHaveBeenCalledWith('hide'),
    )
  })

  it('keeping the page open is one click, because it changes nothing', async () => {
    renderWithProviders(<ArchiveNotice />)
    fireEvent.click(await screen.findByTestId('archive-choose-show'))
    await waitFor(() => expect(keypair.setArchiveChoice).toHaveBeenCalledWith('show'))
  })

  it('offers nothing to decide once the archive is closed', async () => {
    vi.mocked(keypair.getKeypairStatus).mockResolvedValue({
      data: status({
        archive_choice: 'hide',
        archive_notice_seen_at: new Date().toISOString(),
      }),
    } as never)
    renderWithProviders(<ArchiveNotice />)
    const banner = await screen.findByTestId('archive-banner')
    expect(banner.getAttribute('data-state')).toBe('closed')
    expect(screen.queryByTestId('archive-banner-cta')).toBeNull()
  })
})
