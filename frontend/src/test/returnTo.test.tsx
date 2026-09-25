import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { Route, Routes, useLocation } from 'react-router-dom'
import { AFTER_SIGN_IN, afterSignIn, safeReturnUrl, withReturn } from '../lib/returnTo'
import { ProtectedRoute } from '../App'
import WelcomePage from '../pages/WelcomePage'
import { useAuthStore } from '../stores/auth'
import type { User } from '../api/auth'
import { renderWithProviders } from './render'
import i18n from '../i18n'

/**
 * T_UX.30 — the person ends up where they pressed, whatever door they came in by.
 *
 * Ревизия путей R2: a stranger following a recipient link or a friend's invite
 * signed up and landed on the panel, because the link spelled the parameter
 * `next`, the sign-in page read only `returnUrl`, and a new account went to
 * `/welcome` and then the panel regardless. These pin one name, one validator
 * and the hand-over through the two screens a new account passes.
 */
vi.mock('../api/auth', async () => {
  const actual = await vi.importActual<typeof import('../api/auth')>('../api/auth')
  return { ...actual, updateMe: vi.fn(), me: vi.fn() }
})

import { me, updateMe } from '../api/auth'

const t = i18n.t.bind(i18n)

/** Prints where the router ended up, query string included. */
function Where() {
  const location = useLocation()
  return <p data-testid="where">{location.pathname + location.search}</p>
}

const person = {
  id: 'u-new',
  display_name: 'vera',
  email: 'v@b.test',
  email_verified: true,
  active_mode: 'sender',
  roles: [],
} as unknown as User

describe('safeReturnUrl', () => {
  /* GHSA-wrjc-x8rr-h8h6 — the shapes that advisory turns into an off-site
     redirect. Moved here from the sign-in page with its only change being the
     fallback: the panel, not the public front page. */
  it('keeps ordinary in-app paths', () => {
    expect(safeReturnUrl('/invite/abc123')).toBe('/invite/abc123')
    expect(safeReturnUrl('/deals/42?tab=chat')).toBe('/deals/42?tab=chat')
  })

  it('refuses anything that can leave the site', () => {
    for (const hostile of [
      'https://evil.example/steal',
      '//evil.example',
      '/\\evil.example',
      '/path\\..\\elsewhere',
      'javascript:alert(1)',
      'evil.example',
    ]) {
      expect(safeReturnUrl(hostile)).toBe(AFTER_SIGN_IN)
    }
  })

  it('falls back to the panel when there is nothing to return to', () => {
    expect(AFTER_SIGN_IN).toBe('/dashboard')
    expect(safeReturnUrl(null)).toBe('/dashboard')
    expect(safeReturnUrl('')).toBe('/dashboard')
    expect(safeReturnUrl(undefined)).toBe('/dashboard')
  })
})

describe('withReturn', () => {
  it('carries an in-app destination, encoded', () => {
    expect(withReturn('/login', '/join/deal/tok')).toBe('/login?returnUrl=%2Fjoin%2Fdeal%2Ftok')
    expect(withReturn('/login', '/deals/42?tab=chat')).toBe(
      '/login?returnUrl=%2Fdeals%2F42%3Ftab%3Dchat',
    )
  })

  it('carries nothing when the destination is the panel or unsafe', () => {
    expect(withReturn('/login', '/dashboard')).toBe('/login')
    expect(withReturn('/login', null)).toBe('/login')
    expect(withReturn('/login', '//evil.example')).toBe('/login')
  })

  it('joins onto a path that already has a query', () => {
    expect(withReturn('/login?reason=reauth', '/profile')).toBe(
      '/login?reason=reauth&returnUrl=%2Fprofile',
    )
  })
})

describe('afterSignIn', () => {
  it('sends an existing account straight to its destination', () => {
    expect(afterSignIn('/invite/abc')).toBe('/invite/abc')
    expect(afterSignIn(AFTER_SIGN_IN)).toBe('/dashboard')
  })

  it('sends a new account through the welcome screen, destination attached', () => {
    expect(afterSignIn('/join/deal/tok', { created: true })).toBe(
      '/welcome?returnUrl=%2Fjoin%2Fdeal%2Ftok',
    )
    expect(afterSignIn(AFTER_SIGN_IN, { created: true })).toBe('/welcome')
  })

  it('sends an unconfirmed address through confirmation, destination attached', () => {
    expect(afterSignIn('/deals/1/vault', { emailUnverified: true })).toBe(
      '/verify-email?returnUrl=%2Fdeals%2F1%2Fvault',
    )
  })

  it('never lets a hostile destination through', () => {
    expect(afterSignIn('https://evil.example')).toBe('/dashboard')
  })
})

describe('ProtectedRoute', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: null, token: null, authState: 'anonymous' })
  })

  it('remembers the address a signed-out visit was going to', () => {
    renderWithProviders(
      <Routes>
        <Route element={<ProtectedRoute />}>
          <Route path="/deals/:id/vault" element={<p>vault</p>} />
        </Route>
        <Route path="/login" element={<Where />} />
      </Routes>,
      { route: '/deals/d1/vault?from=letter' },
    )
    expect(screen.getByTestId('where').textContent).toBe(
      '/login?returnUrl=%2Fdeals%2Fd1%2Fvault%3Ffrom%3Dletter',
    )
  })

  it('lets a signed-in account through', () => {
    useAuthStore.setState({ user: person, token: 'tok', authState: 'authenticated' })
    renderWithProviders(
      <Routes>
        <Route element={<ProtectedRoute />}>
          <Route path="/deals/:id/vault" element={<p>vault</p>} />
        </Route>
      </Routes>,
      { route: '/deals/d1/vault' },
    )
    expect(screen.getByText('vault')).toBeInTheDocument()
  })
})

describe('WelcomePage', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: person, token: 'tok', authState: 'authenticated' })
    vi.mocked(updateMe).mockReset().mockResolvedValue({ data: person } as never)
    vi.mocked(me).mockReset().mockResolvedValue({ data: person } as never)
  })

  const renderWelcome = (route: string) =>
    renderWithProviders(
      <Routes>
        <Route path="/welcome" element={<WelcomePage />} />
        <Route path="*" element={<Where />} />
      </Routes>,
      { route },
    )

  it('skipping the name still lands on the offer the person came for', async () => {
    renderWelcome('/welcome?returnUrl=%2Fjoin%2Fdeal%2Ftok')
    fireEvent.click(screen.getByRole('button', { name: t('welcome.skip') }))
    expect((await screen.findByTestId('where')).textContent).toBe('/join/deal/tok')
  })

  it('saving the name lands there too', async () => {
    renderWelcome('/welcome?returnUrl=%2Finvite%2Fabc')
    fireEvent.change(screen.getByTestId('welcome-name'), { target: { value: 'Vera' } })
    fireEvent.click(screen.getByRole('button', { name: t('welcome.save') }))
    await waitFor(() => expect(updateMe).toHaveBeenCalled())
    expect((await screen.findByTestId('where')).textContent).toBe('/invite/abc')
  })

  it('goes to the panel when nothing was asked for', async () => {
    renderWelcome('/welcome')
    fireEvent.click(screen.getByRole('button', { name: t('welcome.skip') }))
    expect((await screen.findByTestId('where')).textContent).toBe('/dashboard')
  })
})
