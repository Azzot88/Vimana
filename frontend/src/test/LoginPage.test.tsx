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

  it('shows Sign up link to /register', () => {
    renderWithProviders(<LoginPage />)
    const link = screen.getByRole('link', { name: /sign up/i })
    expect(link).toHaveAttribute('href', '/register')
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
