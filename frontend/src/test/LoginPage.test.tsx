import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import LoginPage, { safeReturnUrl } from '../pages/LoginPage'
import { renderWithProviders } from './render'

describe('LoginPage', () => {
  it('renders title, subtitle, and both inputs', () => {
    renderWithProviders(<LoginPage />)
    expect(screen.getAllByText(/Vimana/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/Sacred Logistics/i)).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/user@example.com/i)).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/••••••••/)).toBeInTheDocument()
  })

  it('offers no separate sign-up — there is nothing to link to', () => {
    // T3.28 pt.3 — one door. A link to a page that no longer exists was the
    // last trace of the two-path shape.
    renderWithProviders(<LoginPage />)
    expect(screen.queryByRole('link', { name: /sign up/i })).not.toBeInTheDocument()
  })

  it('does not force a password — the label says it is optional', () => {
    // The browser used to block submit with "Please fill out this field" on a
    // field captioned «необязательно». A required attribute that contradicts
    // its own label is worse than either alone.
    renderWithProviders(<LoginPage />)
    expect(screen.getByPlaceholderText(/••••••••/)).not.toBeRequired()
  })

  it('renders version badge', () => {
    renderWithProviders(<LoginPage />)
    // Format `v0.<phase:02>.<task>` — match any phase, not just 0.01.
    expect(screen.getByText(/^v0\.\d{2}\./)).toBeInTheDocument()
  })
})

describe('safeReturnUrl', () => {
  /**
   * T_UX.7 pt.2 — the post-login destination is attacker-reachable through the
   * query string, which is precisely what GHSA-wrjc-x8rr-h8h6 turns into an
   * off-site redirect. These are the shapes that advisory is about.
   */
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
      expect(safeReturnUrl(hostile)).toBe('/')
    }
  })

  it('falls back to the front page when there is nothing to return to', () => {
    expect(safeReturnUrl(null)).toBe('/')
    expect(safeReturnUrl('')).toBe('/')
  })
})

// ── T3.28 pt.2 · the one-field door ──────────────────────────────────────────

describe('LoginPage · code flow', () => {
  it('offers no channels until the identifier looks like one', () => {
    renderWithProviders(<LoginPage />)
    expect(screen.queryByTestId('code-channels')).not.toBeInTheDocument()
  })

  it('keeps the password field — accounts made before this flow have one', () => {
    renderWithProviders(<LoginPage />)
    // A screen that quietly stops offering what somebody has used for months
    // reads as a broken site, not as a new feature.
    expect(
      screen.getByPlaceholderText('••••••••'),
    ).toBeInTheDocument()
  })
})
