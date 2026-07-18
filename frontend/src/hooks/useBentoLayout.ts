import { useEffect, useState } from 'react'

export type BentoLayout = 'phone' | 'tablet' | 'desktop'

/** T_UX.1 — единая точка правды для Bento-сетки.
 *
 * Правило: desktop и tablet → 2 колонки, **phone (даже landscape) → 1 колонка**.
 * Причина: телефон в landscape пользователь переворачивает чтобы увидеть
 * содержимое КРУПНЕЕ, а не чтобы получить больше колонок.
 *
 * Tailwind-only breakpoint'ы не подходят: iPhone 14 Pro Max landscape = 932px
 * попадает в `md:` (768+), даёт 2 колонки → нарушение UX-намерения.
 *
 * Логика:
 *   phone   = (max-width: 767px) OR (max-height: 500px AND any-pointer: coarse)
 *   tablet  = 768–1023 AND fine pointer (или coarse без низкой высоты)
 *   desktop = 1024+
 */
export function useBentoLayout(): BentoLayout {
  const compute = (): BentoLayout => {
    if (typeof window === 'undefined') return 'desktop'
    const width = window.innerWidth
    const height = window.innerHeight
    const isCoarse = window.matchMedia('(any-pointer: coarse)').matches

    // Phone: узкая ширина ИЛИ низкая высота + touch (телефон landscape).
    if (width < 768) return 'phone'
    if (height < 500 && isCoarse) return 'phone'

    if (width < 1024) return 'tablet'
    return 'desktop'
  }

  const [layout, setLayout] = useState<BentoLayout>(compute)

  useEffect(() => {
    if (typeof window === 'undefined') return
    const update = () => setLayout(compute())
    window.addEventListener('resize', update)
    window.addEventListener('orientationchange', update)
    return () => {
      window.removeEventListener('resize', update)
      window.removeEventListener('orientationchange', update)
    }
  }, [])

  return layout
}
