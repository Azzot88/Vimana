import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, screen } from '@testing-library/react'
import SecuritySection from '../components/SecuritySection'
import type { User } from '../api/auth'
import { renderWithProviders } from './render'

/**
 * T3.15 — email and password management.
 *
 * The property worth pinning: while a change is in flight the section shows
 * *both* addresses and offers a way out. A UI that swapped the address on
 * request would tell the user the move already happened, which is exactly the
 * lie the two-step backend flow exists to avoid.
 */
vi.mock('../api/auth', async () => {
  const actual = await vi.importActual<typeof import('../api/auth')>('../api/auth')
  return {
    ...actual,
    changeEmail: vi.fn().mockResolvedValue({ data: { status: 'sent' } }),
    cancelEmailChange: vi.fn().mockResolvedValue({ data: { status: 'cancelled' } }),
    changePassword: vi
      .fn()
      .mockResolvedValue({ data: { status: 'changed', access_token: 'fresh-token' } }),
    requestEmailCode: vi.fn().mockResolvedValue({ data: { status: 'sent' } }),
    verifyEmail: vi.fn().mockResolvedValue({ data: { status: 'changed' } }),
    issueRecoveryCodes: vi.fn().mockResolvedValue({
      data: { codes: ['AAAA-BBBB-CCCC', 'DDDD-EEEE-FFFF'], generated_at: 'now' },
    }),
  }
})

const base: User = {
  id: 'u1',
  display_name: 'Nick',
  email: 'old@example.test',
  phone: null,
  can_carry: true,
  can_send: true,
  active_mode: 'sender',
  role: 'user',
  nostr_pubkey: null,
  business_activity_level: null,
  notify_email: true,
  notify_telegram: false,
  notify_whatsapp: false,
  telegram_chat_id: null,
  whatsapp_number: null,
  has_password: true,
  pending_email: null,
}

const noop = () => {}

describe('SecuritySection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows the current address and offers to change it', () => {
    renderWithProviders(<SecuritySection user={base} onChanged={noop} />)
    expect(screen.getByTestId('security-email')).toHaveTextContent('old@example.test')
    expect(screen.getByTestId('security-change-email')).toBeInTheDocument()
  })

  it('offers to set a password when the account has none', () => {
    renderWithProviders(
      <SecuritySection user={{ ...base, has_password: false }} onChanged={noop} />,
    )
    // An account without a password is not second-class — the action is
    // offered, only the wording differs.
    expect(screen.getByTestId('security-change-password')).toBeInTheDocument()
    expect(screen.getByText(/no password/i)).toBeInTheDocument()
  })

  it('keeps the old address visible while a change is pending', () => {
    renderWithProviders(
      <SecuritySection
        user={{ ...base, pending_email: 'new@example.test' }}
        onChanged={noop}
      />,
    )
    expect(screen.getByTestId('security-email')).toHaveTextContent('old@example.test')
    expect(screen.getByText('new@example.test')).toBeInTheDocument()
    expect(screen.getByTestId('security-code')).toBeInTheDocument()
    expect(screen.getByTestId('security-cancel-change')).toBeInTheDocument()
  })

  it('does not prompt for confirmation until the user asks', () => {
    renderWithProviders(<SecuritySection user={base} onChanged={noop} />)
    fireEvent.click(screen.getByTestId('security-change-email'))
    fireEvent.change(screen.getByTestId('security-new-email'), {
      target: { value: 'new@example.test' },
    })
    // A grant is single-use and short-lived: minting one the moment the field
    // parses would spend it on a decision the user has not made.
    expect(screen.queryByTestId('step-up-confirm')).not.toBeInTheDocument()
  })

  it('will not continue with a malformed address', () => {
    renderWithProviders(<SecuritySection user={base} onChanged={noop} />)
    fireEvent.click(screen.getByTestId('security-change-email'))
    fireEvent.change(screen.getByTestId('security-new-email'), {
      target: { value: 'not-an-address' },
    })
    expect(screen.getByTestId('security-email-continue')).toBeDisabled()
  })

  it('will not continue with a password under 8 characters', () => {
    // T_SEC.5 pt.2 — three fields now, so the other two are filled first and
    // the length is the only thing left to fail on. Before that change this
    // test passed with one field; it kept passing for the wrong reason
    // afterwards, which is why the repeat and the current are set explicitly
    // rather than left empty.
    renderWithProviders(<SecuritySection user={base} onChanged={noop} />)
    fireEvent.click(screen.getByTestId('security-change-password'))
    fireEvent.change(screen.getByTestId('security-current-password'), {
      target: { value: 'whatever-the-old-one-is' },
    })
    const field = screen.getByTestId('security-new-password')
    const repeat = screen.getByTestId('security-repeat-password')

    fireEvent.change(field, { target: { value: 'short' } })
    fireEvent.change(repeat, { target: { value: 'short' } })
    expect(screen.getByTestId('security-password-continue')).toBeDisabled()

    fireEvent.change(field, { target: { value: 'long-enough-1' } })
    fireEvent.change(repeat, { target: { value: 'long-enough-1' } })
    expect(screen.getByTestId('security-password-continue')).not.toBeDisabled()
  })

  it('will not continue while the two passwords differ', () => {
    renderWithProviders(<SecuritySection user={base} onChanged={noop} />)
    fireEvent.click(screen.getByTestId('security-change-password'))
    fireEvent.change(screen.getByTestId('security-current-password'), {
      target: { value: 'old-password-1' },
    })
    fireEvent.change(screen.getByTestId('security-new-password'), {
      target: { value: 'long-enough-1' },
    })
    fireEvent.change(screen.getByTestId('security-repeat-password'), {
      target: { value: 'long-enough-2' },
    })

    expect(screen.getByTestId('security-password-mismatch')).toBeInTheDocument()
    expect(screen.getByTestId('security-password-continue')).toBeDisabled()
  })

  it('asks for no current password when the account has none', () => {
    // A passkey or Nostr account has nothing to type there, and the proof
    // comes from the step-up dialog instead.
    renderWithProviders(
      <SecuritySection user={{ ...base, has_password: false }} onChanged={noop} />,
    )
    fireEvent.click(screen.getByTestId('security-change-password'))
    expect(
      screen.queryByTestId('security-current-password'),
    ).not.toBeInTheDocument()
  })

  it('warns that other devices will be signed out, before the action', () => {
    renderWithProviders(<SecuritySection user={base} onChanged={noop} />)
    // Not discovered afterwards: the consequence is on screen while the user
    // is still deciding.
    expect(screen.queryByTestId('security-sessions-warning')).not.toBeInTheDocument()
    fireEvent.click(screen.getByTestId('security-change-password'))
    expect(screen.getByTestId('security-sessions-warning')).toBeInTheDocument()
    expect(screen.getByText(/signed out/i)).toBeInTheDocument()
  })

  it('cancelling a pending change calls the API', async () => {
    const { cancelEmailChange } = await import('../api/auth')
    renderWithProviders(
      <SecuritySection
        user={{ ...base, pending_email: 'new@example.test' }}
        onChanged={noop}
      />,
    )
    fireEvent.click(screen.getByTestId('security-cancel-change'))
    expect(cancelEmailChange).toHaveBeenCalled()
  })

  // ── T3.16 — recovery codes ────────────────────────────────────────────────

  it('says how many codes are left and warns while it can still be fixed', () => {
    renderWithProviders(
      <SecuritySection user={{ ...base, recovery_codes_remaining: 2 }} onChanged={noop} />,
    )
    expect(screen.getByTestId('recovery-left')).toHaveTextContent('2')
    // Two is already low: the warning has to arrive while signing in still
    // works, not once the last code is gone.
    expect(screen.getByTestId('recovery-warning')).toBeInTheDocument()
  })

  it('does not nag while the account has codes to spare', () => {
    renderWithProviders(
      <SecuritySection user={{ ...base, recovery_codes_remaining: 10 }} onChanged={noop} />,
    )
    expect(screen.queryByTestId('recovery-warning')).not.toBeInTheDocument()
  })

  it('asks for confirmation before replacing a set', () => {
    renderWithProviders(
      <SecuritySection user={{ ...base, recovery_codes_remaining: 10 }} onChanged={noop} />,
    )
    // Generating replaces the previous set, so it goes through step-up like
    // every other change here — the codes are a way in, and minting new ones
    // from a stolen session would outlive the password change meant to end it.
    expect(screen.queryByTestId('step-up-confirm')).not.toBeInTheDocument()
    fireEvent.click(screen.getByTestId('recovery-generate'))
    expect(screen.getByTestId('step-up-confirm')).toBeInTheDocument()
  })
})
