import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { act, fireEvent, screen } from '@testing-library/react'
import AuthBootstrap from '../components/AuthBootstrap'
import { useAuthStore } from '../stores/auth'
import { renderWithProviders } from './render'

/**
 * T3.11.27 — «сделай предупреждение о неактивности не через две минуты, а через
 * 25» (owner, 2026-09-12).
 *
 * The number itself is the whole feature, which is why it is worth a test: a
 * panel that interrupts somebody four minutes into reading a deal is indistin-
 * guishable, from the outside, from the app logging them out at random — and
 * that is what the owner met. Nothing fails when a constant drifts; the modal
 * simply starts arriving earlier.
 *
 * The old value was expressed as a *distance from the end* («two minutes
 * before»), so it moved with `INACTIVITY_MS`. These tests pin it as a moment.
 */
vi.mock('../api/auth', async () => {
  const actual = await vi.importActual<typeof import('../api/auth')>('../api/auth')
  return {
    ...actual,
    me: vi.fn().mockResolvedValue({ data: { id: 'u1', active_mode: 'sender' } }),
    logout: vi.fn().mockResolvedValue({ data: {} }),
  }
})

const MINUTE = 60 * 1000

/** Signed in, and idle for exactly this long. */
async function signedInIdleFor(ms: number) {
  useAuthStore.setState({ token: 'tok', authState: 'loading' })
  renderWithProviders(
    <AuthBootstrap>
      <p>deal</p>
    </AuthBootstrap>,
  )
  // `hydrate()` resolves on a microtask and stamps `lastActivityAt` itself, so
  // the idleness is staged after it, never before.
  await act(async () => {})
  act(() => {
    useAuthStore.setState({ lastActivityAt: Date.now() - ms })
  })
  // One turn of the 30-second checker.
  act(() => {
    vi.advanceTimersByTime(30 * 1000)
  })
}

const warning = () =>
  screen.queryByText(/logged out soon|Скоро выход из системы/i)

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
})

afterEach(() => {
  vi.useRealTimers()
  useAuthStore.setState({ token: null, user: null, authState: 'loading' })
})

describe('the inactivity warning', () => {
  it('stays out of the way at twenty-four minutes', async () => {
    await signedInIdleFor(24 * MINUTE)
    expect(warning()).not.toBeInTheDocument()
  })

  it('arrives at twenty-five, five minutes before the logout', async () => {
    await signedInIdleFor(25 * MINUTE)
    expect(warning()).toBeInTheDocument()
  })

  it('does not arrive at two, which is where it used to', async () => {
    await signedInIdleFor(2 * MINUTE)
    expect(warning()).not.toBeInTheDocument()
  })

  it('goes away the moment somebody moves, and the clock starts over', async () => {
    await signedInIdleFor(25 * MINUTE)
    expect(warning()).toBeInTheDocument()

    fireEvent.mouseMove(window)
    expect(warning()).not.toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(30 * 1000)
    })
    expect(warning()).not.toBeInTheDocument()
  })

  it('asks nothing of somebody who is not signed in', async () => {
    useAuthStore.setState({ token: null, authState: 'loading' })
    renderWithProviders(
      <AuthBootstrap>
        <p>deal</p>
      </AuthBootstrap>,
    )
    await act(async () => {})
    act(() => {
      useAuthStore.setState({ lastActivityAt: Date.now() - 40 * MINUTE })
      vi.advanceTimersByTime(60 * 1000)
    })
    expect(warning()).not.toBeInTheDocument()
  })
})
