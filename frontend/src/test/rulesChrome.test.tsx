import { beforeEach, describe, expect, it } from 'vitest'
import { fireEvent, screen } from '@testing-library/react'
import LandingShell from '../components/landing/LandingShell'
import type { User } from '../api/auth'
import { useAuthStore } from '../stores/auth'
import { renderWithProviders } from './render'
import i18n from '../i18n'

/**
 * T_UX.40 — the rules pages wear the app's own shell for a signed-in reader.
 *
 * Pinned: a signed-in reader keeps the navigation they arrived through
 * («Правила» is a link in it), a guest keeps the public frame the server
 * renders, the waitlist dialog opens in both, and the pages that did not ask
 * for the switch — the landing and the audience pages — are untouched.
 */
const t = i18n.t.bind(i18n)

const member = {
  id: 'u-1',
  display_name: 'Reader',
  roles: [],
  active_mode: 'sender',
  can_carry: true,
  can_send: true,
} as unknown as User

const page = (open: () => void, frame?: string) => (
  <div>
    <p>rules body</p>
    <p>frame:{frame}</p>
    <button type="button" onClick={open}>
      packet
    </button>
  </div>
)

describe('LandingShell with appChromeWhenSignedIn', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: null, token: null, authState: 'anonymous' })
  })

  it('gives a guest the public frame, footer links included', () => {
    renderWithProviders(
      <LandingShell source="sender" appChromeWhenSignedIn>
        {page}
      </LandingShell>,
    )
    expect(screen.getByText('rules body')).toBeInTheDocument()
    expect(screen.getByText('frame:landing')).toBeInTheDocument()
    expect(screen.getByText(`Vimana · ${t('landing.footerTagline')}`)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: t('nav.dashboard') })).not.toBeInTheDocument()
  })

  it('gives a signed-in reader the app navigation instead', () => {
    useAuthStore.getState().setAuth(member, 'token-1')
    renderWithProviders(
      <LandingShell source="sender" appChromeWhenSignedIn>
        {page}
      </LandingShell>,
    )
    expect(screen.getByText('rules body')).toBeInTheDocument()
    expect(screen.getByText('frame:app')).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: t('nav.rules') }).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('link', { name: t('nav.dashboard') }).length).toBeGreaterThan(0)
    expect(
      screen.queryByText(`Vimana · ${t('landing.footerTagline')}`),
    ).not.toBeInTheDocument()
  })

  it('still opens the waitlist dialog inside the app shell', () => {
    useAuthStore.getState().setAuth(member, 'token-1')
    renderWithProviders(
      <LandingShell source="sender" appChromeWhenSignedIn>
        {page}
      </LandingShell>,
    )
    fireEvent.click(screen.getByText('packet'))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('leaves pages without the flag in the public frame for a signed-in visitor', () => {
    useAuthStore.getState().setAuth(member, 'token-1')
    renderWithProviders(<LandingShell source="landing">{page}</LandingShell>)
    expect(screen.getByRole('link', { name: t('landing.ctaDashboard') })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: t('nav.rules') })).not.toBeInTheDocument()
  })
})
