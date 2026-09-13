import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { useLiveBeat, LIVE_BEAT_MS } from './useLiveBeat'

/**
 * T3.11.27 — the beat both live screens run on.
 *
 * Worth its own tests because every property here is invisible when it breaks:
 * a torn-down timer just stops updating, a beat that ignores `visibilityState`
 * just costs battery, and a stale callback keeps refetching with yesterday's
 * chat id. Nothing throws in any of those cases.
 */
let visible = 'visible'

beforeEach(() => {
  vi.useFakeTimers()
  visible = 'visible'
  Object.defineProperty(document, 'visibilityState', {
    configurable: true,
    get: () => visible,
  })
})

afterEach(() => {
  vi.useRealTimers()
})

const tick = (ms = LIVE_BEAT_MS) => act(() => void vi.advanceTimersByTime(ms))

describe('useLiveBeat', () => {
  it('asks again once the interval is up', () => {
    const beat = vi.fn()
    renderHook(() => useLiveBeat(beat))
    expect(beat).not.toHaveBeenCalled() // the first load is the caller's own
    tick()
    expect(beat).toHaveBeenCalledTimes(1)
    tick()
    expect(beat).toHaveBeenCalledTimes(2)
  })

  it('keeps quiet while the tab is hidden', () => {
    const beat = vi.fn()
    renderHook(() => useLiveBeat(beat))
    visible = 'hidden'
    tick()
    tick()
    expect(beat).not.toHaveBeenCalled()
  })

  it('refreshes the moment the tab comes back, without waiting out the interval', () => {
    const beat = vi.fn()
    renderHook(() => useLiveBeat(beat))
    visible = 'hidden'
    tick()
    visible = 'visible'
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'))
    })
    expect(beat).toHaveBeenCalledTimes(1)
  })

  it('runs the callback it has now, not the one it was mounted with', () => {
    /* Every caller rebuilds this function on each render. Holding it in a ref is
       what lets the interval survive; forgetting to update that ref would leave
       the screen refetching the deal somebody opened ten minutes ago. */
    const first = vi.fn()
    const second = vi.fn()
    const { rerender } = renderHook(({ fn }) => useLiveBeat(fn), {
      initialProps: { fn: first },
    })
    rerender({ fn: second })
    tick()
    expect(first).not.toHaveBeenCalled()
    expect(second).toHaveBeenCalledTimes(1)
  })

  it('does nothing at all when it is not switched on', () => {
    // `Boolean(dealId)` — a screen without an id has nothing to ask about.
    const beat = vi.fn()
    renderHook(() => useLiveBeat(beat, false))
    tick()
    expect(beat).not.toHaveBeenCalled()
  })

  it('stops when the screen goes away', () => {
    const beat = vi.fn()
    const { unmount } = renderHook(() => useLiveBeat(beat))
    unmount()
    tick()
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'))
    })
    expect(beat).not.toHaveBeenCalled()
  })
})
