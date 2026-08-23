import { describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import LoginPage, { safeReturnUrl } from '../pages/LoginPage'
import { renderWithProviders } from './render'

/** The page asks the server two questions, and neither is what this file is
 *  about.
 *
 *  `contactChannels('')` fires on mount — "which channels work with nothing
 *  typed yet". Unmocked in jsdom that becomes a real XHR to a host nobody is
 *  listening on; the component's `.catch` swallows the rejection, so the tests
 *  passed while every render printed a jsdom `AggregateError` to stderr. Six
 *  renders, six errors, all of them noise that trained the eye to skip stderr.
 *
 *  Empty on purpose — the same answer the failing request produced, so nothing
 *  about these assertions changes. Telegram would render an extra button and
 *  quietly rewrite what four of these tests are looking at.
 *
 *  `loginMethods` is debounced behind a typed identifier and no test here types
 *  one, but it is stubbed too: the next test that fills the field should not
 *  have to rediscover why stderr went red. */
vi.mock('../api/auth', async () => {
  const actual = await vi.importActual<typeof import('../api/auth')>('../api/auth')
  return {
    ...actual,
    contactChannels: vi.fn().mockResolvedValue({ data: { channels: [] } }),
    loginMethods: vi
      .fn()
      .mockResolvedValue({ data: { methods: [], can_reset: false } }),
  }
})

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
