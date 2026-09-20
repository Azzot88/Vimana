import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { act, fireEvent, screen } from '@testing-library/react'
import AuthBootstrap from '../components/AuthBootstrap'
import { useAuthStore } from '../stores/auth'
import { renderWithProviders } from './render'

/**
 * T_SEC.7 (owner, 2026-09-20) — «30 days inactive → logout».
 *
 * The timer answers one question now: when does a device stop being remembered.
 * Identity is a separate clock the server keeps — a session older than a day is
 * asked to prove itself again — so throwing somebody out mid-afternoon protects
 * nothing and was the complaint that started this.
 *
 * Two of these tests pin the *old* behaviour as gone: twenty-five minutes of
 * reading must be silent. The rest pin what activity means, because the defect
 * behind the report was there — `scroll` does not bubble, so reading a deal's
 * conversation with the wheel counted as idleness, and a screen polling the
 * server counted as nothing at all.
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
const DAY = 24 * 60 * MINUTE
/** The default in `AuthBootstrap`, restated so a drift shows up here. */
const LIMIT = 30 * DAY

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
  it('says nothing after half an hour of reading — that limit is gone', async () => {
    await signedInIdleFor(25 * MINUTE)
    expect(warning()).not.toBeInTheDocument()
  })

  it('says nothing after a day, because a day is the server’s question', async () => {
    await signedInIdleFor(DAY + MINUTE)
    expect(warning()).not.toBeInTheDocument()
  })

  it('arrives five minutes before the thirty days are up', async () => {
    await signedInIdleFor(LIMIT - 4 * MINUTE)
    expect(warning()).toBeInTheDocument()
  })

  it('has not arrived six minutes before that', async () => {
    await signedInIdleFor(LIMIT - 6 * MINUTE)
    expect(warning()).not.toBeInTheDocument()
  })

  it('goes away the moment somebody moves, and the clock starts over', async () => {
    await signedInIdleFor(LIMIT - 4 * MINUTE)
    expect(warning()).toBeInTheDocument()

    fireEvent.mouseMove(window)
    expect(warning()).not.toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(30 * 1000)
    })
    expect(warning()).not.toBeInTheDocument()
  })

  it('counts a request to the server as activity', async () => {
    // The defect this fixes: a deal screen polls on its own, and the person
    // reading it was «idle» because the pointer had not moved.
    await signedInIdleFor(LIMIT - 4 * MINUTE)
    expect(warning()).toBeInTheDocument()

    act(() => {
      window.dispatchEvent(new Event('api-activity'))
    })
    expect(warning()).not.toBeInTheDocument()
  })

  it('counts scrolling inside the page, which does not reach the window', async () => {
    await signedInIdleFor(LIMIT - 4 * MINUTE)
    expect(warning()).toBeInTheDocument()

    // Dispatched on an element, not on `window`: `scroll` does not bubble, so
    // only a capturing listener sees it — which is the fix.
    act(() => {
      const inner = document.createElement('div')
      document.body.appendChild(inner)
      inner.dispatchEvent(new Event('scroll'))
      inner.remove()
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
      useAuthStore.setState({ lastActivityAt: Date.now() - LIMIT })
      vi.advanceTimersByTime(60 * 1000)
    })
    expect(warning()).not.toBeInTheDocument()
  })
})
