import { describe, it, expect, beforeEach, vi } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useBentoLayout } from './useBentoLayout'

/** T_UX.1 — verify the phone-landscape edge case that motivated the hook.
 *
 *  iPhone 14 Pro Max landscape = 932 × 430 with a coarse pointer. Tailwind
 *  width-only breakpoints would classify this as `md:` (768+) → 2 columns,
 *  which is the wrong UX. Our hook must return 'phone'. */

function mockWindow(width: number, height: number, coarse: boolean) {
  Object.defineProperty(window, 'innerWidth', { value: width, configurable: true })
  Object.defineProperty(window, 'innerHeight', { value: height, configurable: true })
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: query.includes('coarse') ? coarse : false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }))
}

describe('useBentoLayout', () => {
  beforeEach(() => {
    // reset window sizes between tests
    mockWindow(1440, 900, false)
  })

  it('returns "desktop" for large screens with fine pointer', () => {
    mockWindow(1440, 900, false)
    const { result } = renderHook(() => useBentoLayout())
    expect(result.current).toBe('desktop')
  })

  it('returns "tablet" for 768-1023 width with fine pointer', () => {
    mockWindow(900, 700, false)
    const { result } = renderHook(() => useBentoLayout())
    expect(result.current).toBe('tablet')
  })

  it('returns "phone" for narrow width regardless of pointer', () => {
    mockWindow(400, 800, true)
    const { result } = renderHook(() => useBentoLayout())
    expect(result.current).toBe('phone')
  })

  it('returns "phone" for iPhone 14 Pro Max landscape (932x430 coarse)', () => {
    // The whole reason this hook exists.
    mockWindow(932, 430, true)
    const { result } = renderHook(() => useBentoLayout())
    expect(result.current).toBe('phone')
  })

  it('returns "tablet" for iPad portrait (768x1024 coarse)', () => {
    mockWindow(768, 1024, true)
    const { result } = renderHook(() => useBentoLayout())
    expect(result.current).toBe('tablet')
  })
})
